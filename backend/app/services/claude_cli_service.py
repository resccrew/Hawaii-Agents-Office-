"""Async subprocess wrapper around headless `claude -p --resume`.

Empirically validated in isolation before this file was written (see
compiled-dreaming-badger.md Phase 3 step 1 and the manual test transcript
in scratchpad/chat-bridge-test/): `claude -p "<msg>" --resume <session_id>
--output-format stream-json --verbose` injects a new user turn into an
existing session and streams back newline-delimited JSON. `--verbose` is
mandatory — the CLI rejects `--output-format stream-json` under `--print`
without it. Confirmed the resumed session correctly recalls prior turns
(conversation continuity across separate process invocations).

Also empirically found (not anticipated in the original plan): `--resume`
is tied to the `cwd` the session was created in — resuming from a
different directory fails immediately with "No conversation found with
session ID: ...". Callers MUST pass the session's original working
directory as `cwd`; StateMachine.working_dir (captured from hook event
payloads) is the source of truth chat_bridge.py uses for this.

This module treats CLI stdout as untrusted external input: every line is
JSON-decoded defensively, non-JSON lines are skipped, and a hard timeout
bounds the whole call. It does not decide WHEN it's safe to call — that
policy (checking `interactive_turn_active`) lives in chat_bridge.py.

Known open risk (flagged in the plan, not solved here): this process is a
second writer to the same on-disk session transcript the interactive CLI
may also be writing to. `claude`'s own permission-mode for the resumed
session's settings applies to headless turns too — if a headless turn
would trigger a permission prompt, `claude -p` cannot prompt (there's no
TTY) and the call will hang until `timeout_seconds` kills it.

Bugfix pass: callers may now pass `permission_mode` explicitly (e.g.
"bypassPermissions"). This module does NOT default it — the caller decides,
because the right answer differs by who's on the other end: chat_bridge.py
only sets it for Phase-6-spawned agents running in their own isolated
workspace directory (never for a hook-observed interactive session, where
silently bypassing permissions on a human's real project would be an actual
safety regression, not a convenience).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

ChunkKind = Literal["text_delta", "turn_complete", "error"]


@dataclass
class ChatChunk:
    kind: ChunkKind
    text: str = ""
    raw: dict[str, Any] | None = None


class ClaudeCliError(RuntimeError):
    """Raised when the CLI is missing, exits non-zero, or times out."""


async def send_headless_message(
    session_id: str,
    message: str,
    *,
    cwd: str | None = None,
    timeout_seconds: float = 120.0,
    mcp_config_path: str | None = None,
    permission_mode: str | None = None,
) -> AsyncIterator[ChatChunk]:
    """Yield ChatChunks parsed from `claude -p --resume` stream-json output.

    Raises ClaudeCliError on: binary not found, non-zero exit, or timeout.
    Malformed individual JSON lines are skipped, not fatal to the call.

    `mcp_config_path` (Phase 6): when set, passes `--mcp-config` so this
    turn has the studio-ops MCP tools available (list_agents, send_message,
    create_task, ...) — needed on every resumed turn, not just spawn, since
    each `claude -p` invocation is a fresh process with no memory of a
    previous invocation's flags.

    `permission_mode`: when set, passes `--permission-mode <value>` (e.g.
    "bypassPermissions"). See module docstring — caller's responsibility to
    decide when this is safe.
    """
    args = [
        "claude",
        "-p",
        message,
        "--resume",
        session_id,
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if mcp_config_path:
        args += ["--mcp-config", mcp_config_path]
    if permission_mode:
        args += ["--permission-mode", permission_mode]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ClaudeCliError("claude CLI not found on PATH") from exc

    async def _read_lines() -> AsyncIterator[ChatChunk]:
        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue  # defensive: never let a malformed line kill the stream

            obj_type = obj.get("type")
            if obj_type == "assistant":
                content = obj.get("message", {}).get("content", [])
                text = "".join(
                    block.get("text", "") for block in content if block.get("type") == "text"
                )
                if text:
                    yield ChatChunk(kind="text_delta", text=text, raw=obj)
            elif obj_type == "result":
                if obj.get("is_error"):
                    # "result" is often absent on error (e.g. session/cwd
                    # mismatch reports via "errors" instead) — fall back to
                    # that so failures are diagnosable instead of a bare
                    # "unknown error".
                    error_text = obj.get("result") or "; ".join(obj.get("errors", [])) or "unknown error"
                    yield ChatChunk(kind="error", text=error_text, raw=obj)
                else:
                    yield ChatChunk(kind="turn_complete", text=obj.get("result", ""), raw=obj)

    try:
        async with asyncio.timeout(timeout_seconds):
            async for chunk in _read_lines():
                yield chunk
            returncode = await proc.wait()
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise ClaudeCliError(
            f"claude -p --resume timed out after {timeout_seconds}s "
            "(possibly blocked on a permission prompt with no TTY to answer it)"
        ) from exc

    if returncode != 0:
        stderr = b""
        if proc.stderr is not None:
            stderr = await proc.stderr.read()
        raise ClaudeCliError(
            f"claude -p --resume exited {returncode}: {stderr.decode('utf-8', errors='replace')[:500]}"
        )


@dataclass
class SpawnedSession:
    session_id: str
    result_text: str


async def spawn_new_session(
    initial_prompt: str,
    *,
    cwd: str,
    timeout_seconds: float = 180.0,
    mcp_config_path: str | None = None,
    permission_mode: str | None = None,
) -> SpawnedSession:
    """Create a brand-new headless session (Phase 6 Add-Agent flow) — no
    --resume, since there's nothing to resume yet. Uses --output-format
    json (single object, not streaming) since the caller needs the
    generated session_id before a chat WS channel can even be opened; the
    UI shows a "starting..." state for this one call, then switches to the
    normal streaming send_headless_message path for every turn after.
    """
    args = ["claude", "-p", initial_prompt, "--output-format", "json"]
    if mcp_config_path:
        args += ["--mcp-config", mcp_config_path]
    if permission_mode:
        args += ["--permission-mode", permission_mode]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ClaudeCliError("claude CLI not found on PATH") from exc

    try:
        async with asyncio.timeout(timeout_seconds):
            stdout, stderr = await proc.communicate()
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise ClaudeCliError(f"claude -p (spawn) timed out after {timeout_seconds}s") from exc

    if proc.returncode != 0:
        raise ClaudeCliError(
            f"claude -p (spawn) exited {proc.returncode}: "
            f"{stderr.decode('utf-8', errors='replace')[:500]}"
        )

    try:
        obj = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ClaudeCliError("claude -p (spawn) returned non-JSON output") from exc

    if obj.get("is_error"):
        error_text = obj.get("result") or "; ".join(obj.get("errors", [])) or "unknown error"
        raise ClaudeCliError(f"claude -p (spawn) reported an error: {error_text}")

    session_id = obj.get("session_id")
    if not session_id:
        raise ClaudeCliError("claude -p (spawn) response had no session_id")

    return SpawnedSession(session_id=session_id, result_text=obj.get("result", ""))
