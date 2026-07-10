"""Configuration loading and constants for the Studio Ops hooks.

Ported from claude-office's hooks/src/claude_office_hooks/config.py, env
vars renamed CLAUDE_OFFICE_* -> STUDIO_OPS_*, default port changed to 8010
(studio-ops runs on an isolated port from claude-office's 8000, per the
Phase 2 discovery that binding the same ports as an already-running
claude-office instance silently shadows its traffic).

IMPORTANT: This module must not produce any stdout/stderr output.
"""

import os
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

_LOCALHOST_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1", None})
_DEFAULT_API_URL = "http://localhost:8010/api/v1/events"


def _resolve_api_url(
    raw_url: str,
    allow_remote: bool,
    on_clamp: Callable[[str | None], None],
) -> str:
    """Loopback clamp: event payloads can carry tool inputs/outputs and file
    paths, so a non-localhost API URL is reset to the local default unless
    explicitly opted into via STUDIO_OPS_ALLOW_REMOTE=1."""
    host = urlparse(raw_url).hostname
    if host in _LOCALHOST_HOSTNAMES:
        return raw_url
    if allow_remote:
        return raw_url
    on_clamp(host)
    return _DEFAULT_API_URL


def _log_clamp(host: str | None) -> None:
    try:
        from studio_ops_hooks.debug_logger import log_notice

        log_notice(
            f"STUDIO_OPS_API_URL is non-localhost ('{host}'); clamped to the "
            f"local default. Set STUDIO_OPS_ALLOW_REMOTE=1 to use a remote backend.",
            context="config",
        )
    except Exception:
        pass


API_URL = _resolve_api_url(
    os.environ.get("STUDIO_OPS_API_URL", _DEFAULT_API_URL),
    os.environ.get("STUDIO_OPS_ALLOW_REMOTE", "") == "1",
    _log_clamp,
)

_api_key_holder: list[str] = [""]
TIMEOUT = 0.5  # Seconds — keep short so hooks never block Claude


def get_api_key() -> str:
    return _api_key_holder[0]


def _set_api_key(key: str) -> None:
    _api_key_holder[0] = key


CONFIG_FILE = Path.home() / ".claude" / "studio-ops-config.env"

STRIP_PREFIXES: list[str] = []


def load_config() -> dict[str, str]:
    config: dict[str, str] = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        value = value.strip().strip('"').strip("'")
                        config[key.strip()] = value
        except Exception:
            pass
    _set_api_key(os.environ.get("STUDIO_OPS_API_KEY", config.get("STUDIO_OPS_API_KEY", "")))
    return config
