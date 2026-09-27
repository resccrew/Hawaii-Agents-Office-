"""Shared API token — the single gate every REST route and WebSocket in this
app sits behind. Closes the "no auth at all" hole docs/review/backend.md
flagged as C1, most severely for /ws/terminal: without this, any local
process that can reach :8010 could write raw bytes into a real PTY, i.e. an
unauthenticated shell.

The token lives at ~/.studio-ops/api-token: 32 random bytes, hex-encoded,
generated once on first backend start and reused after that (dir 0700, file
0600 — same discipline as an SSH key). hooks/, the MCP server
(app/mcp/studio_ops_mcp.py), and the Tauri sidecar's `get_api_token` command
all read this one file instead of needing their own distribution mechanism.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import secrets
from pathlib import Path

from fastapi import Header, HTTPException, WebSocket, WebSocketException, status

TOKEN_DIR = Path.home() / ".studio-ops"
TOKEN_FILE = TOKEN_DIR / "api-token"

# Origins a WebSocket is allowed to present. A browser always sends Origin;
# the Tauri webview sends one of the first three depending on platform/dev
# vs. packaged build. Anything else present is rejected outright — a
# malicious page in an unrelated browser tab cannot reach this socket even
# if it somehow obtained a valid token. Absent Origin (no browser involved
# at all — hooks, the MCP server's future WS use, curl/websocat) is allowed
# through to the token check instead, since non-browser HTTP/WS clients
# never send one.
ALLOWED_WS_ORIGINS = frozenset(
    {
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://localhost:3010",
    }
)

_token_cache: str | None = None


def get_token() -> str:
    """Read the shared token, generating it on first call. Cached in-process
    for the life of the backend — the file only changes if a human deletes
    it (next start regenerates).

    Directory and file are created with their final restrictive mode set
    atomically at creation time (`mkdir(mode=...)` under a tightened umask,
    `os.open` with O_CREAT|O_EXCL and an explicit mode) rather than created
    permissively and `chmod`ed afterwards — the latter leaves a window,
    however brief, where another local process could open the token file
    before its permissions are tightened."""
    global _token_cache
    if _token_cache is not None:
        return _token_cache

    if TOKEN_FILE.exists():
        existing = TOKEN_FILE.read_text().strip()
        if existing:
            _token_cache = existing
            return _token_cache

    old_umask = os.umask(0o077)
    try:
        TOKEN_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
        token = secrets.token_hex(32)
        try:
            fd = os.open(TOKEN_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            # Lost a startup race to another process — read what it wrote
            # rather than clobbering a token something else may already be
            # relying on.
            existing = TOKEN_FILE.read_text().strip()
            _token_cache = existing
            return _token_cache
        try:
            os.write(fd, token.encode())
        finally:
            os.close(fd)
    finally:
        os.umask(old_umask)

    _token_cache = token
    return token


def token_matches(candidate: str | None) -> bool:
    """Constant-time comparison — a naive `==` here would leak the token one
    byte at a time via response-timing, same class of bug a login form's
    password check has to avoid."""
    if not candidate:
        return False
    return hmac.compare_digest(candidate, get_token())


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """REST dependency — mount with `dependencies=[Depends(require_api_key)]`
    on a router include so every route under it needs a valid X-API-Key,
    without threading the check through each handler individually."""
    if not token_matches(x_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing X-API-Key")


async def enforce_ws_auth(websocket: WebSocket) -> None:
    """WebSocket dependency — add `_: None = Depends(enforce_ws_auth)` to a
    `@router.websocket(...)` handler's signature. Raising WebSocketException
    here (FastAPI's documented mechanism for this exact case) closes the
    connection with that code before the handler body — and therefore
    before `websocket.accept()` — ever runs.

    Origin is checked first: a browser always sends one, so a mismatch (or
    a value outside the allowlist) is rejected regardless of token, since a
    page from an origin that has no business talking to this app shouldn't
    be able to brute-force the token from there. A client with no Origin at
    all (hooks, CLI tools, non-browser callers) skips that check and is
    gated on the token alone.
    """
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in ALLOWED_WS_ORIGINS:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    token = websocket.query_params.get("token")
    if not token_matches(token):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)


_TOKEN_QUERY_RE = re.compile(r"(token=)[^&\s\"]+")


class _MaskWsTokenFilter(logging.Filter):
    """The only way a browser WebSocket can present the token is in the URL
    (`?token=...` — WS clients can't set custom headers), so it's the one
    place the real value legitimately travels. uvicorn's access log would
    otherwise write that same URL, query string and all, to disk on every
    connection — leaking the token into a log file with much looser
    permissions (or a log aggregator) than api-token's 0600. Masks it in
    place instead of disabling access logging altogether, since REST access
    logs are still useful for debugging."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            return True
        if "/ws/" in message and "token=" in message:
            record.msg = _TOKEN_QUERY_RE.sub(r"\1***", message)
            record.args = ()
        return True


def install_ws_log_token_mask() -> None:
    """Call once at startup (app.main does, at import time) — idempotent."""
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _MaskWsTokenFilter) for f in access_logger.filters):
        access_logger.addFilter(_MaskWsTokenFilter())
