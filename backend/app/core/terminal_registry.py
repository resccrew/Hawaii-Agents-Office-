"""Terminal pane registry — in-memory only, unlike every other registry in
this codebase (agent_registry, task_board, and workspace_registry all
persist a JSON snapshot). Deliberately NOT persisted: a TerminalPane's only
reason to exist is the live PTY process behind it, and that process dies
with the backend — a snapshot that outlived it would just be a pane-shaped
lie on restart. Panes disappear on backend restart; the human reopens
whatever they still need, same accepted limitation noted in the Phase 3
plan (no attempt to resurrect real OS processes across a restart).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from app.core.connection_manager import get_manager
from app.models.terminal import TerminalKind, TerminalPane
from app.services import terminal_service
from app.services.terminal_service import PtyProcess

# None = the user's own $SHELL (see terminal_service.spawn's default).
_COMMANDS: dict[str, list[str] | None] = {
    "shell": None,
    "claude": ["claude"],
    "codex": ["codex"],
    "antigravity": ["gemini"],
}


@dataclass
class LivePane:
    pane: TerminalPane
    proc: PtyProcess


class TerminalRegistry:
    def __init__(self) -> None:
        self._panes: dict[str, LivePane] = {}

    async def create(self, *, workspace_id: str, kind: TerminalKind, cwd: str) -> TerminalPane:
        pane_id = f"pane-{uuid.uuid4().hex[:10]}"
        cmd = _COMMANDS.get(kind)
        env = None

        if kind == "claude":
            from app.core.agent_registry import get_agent_registry
            from app.core.agent_spawner import _emit_session_start
            import os
            
            # Auto-register an agent session so the interactive terminal
            # has full MCP capabilities and appears on the Board.
            registry = get_agent_registry()
            agent = registry.create(
                provider="claude",
                department_id="Engineering",
                role="Terminal Operator",
                name=f"Term {pane_id[-4:]}",
            )
            # Claude generates its own session ID unless we provide one.
            # We enforce our own ID so we can link the hook events to this agent.
            claude_session_id = f"term-{uuid.uuid4().hex}"
            agent.claude_session_id = claude_session_id
            agent.status = "active"
            registry.save()

            # Pass the MCP config to the interactive PTY
            cmd = ["claude", "--mcp-config", str(agent.mcp_config_path)]
            
            # Pass the enforced session ID in the environment so the hook script captures it
            env = os.environ.copy()
            env["CLAUDE_SESSION_ID"] = claude_session_id
            
            # Emit start so it appears on the board immediately
            await _emit_session_start(agent)

        proc = terminal_service.spawn(cwd, cmd, env=env)
        pane = TerminalPane(id=pane_id, workspace_id=workspace_id, kind=kind)
        self._panes[pane_id] = LivePane(pane=pane, proc=proc)

        manager = get_manager()

        def on_output(data: bytes) -> None:
            asyncio.create_task(manager.broadcast_terminal_bytes(pane_id, data))

        def on_exit() -> None:
            self.mark_exited(pane_id)

        # Wired up here, at creation, rather than lazily on first WS connect
        # — a pane's output starts flowing immediately, so nothing is lost
        # to a race between "process spawned" and "browser tab connected"
        # beyond whatever arrived before the very first WS attaches (there's
        # no scrollback replay in this initial implementation; a client that
        # connects late just starts seeing output from that point on).
        terminal_service.start_reading(proc, on_output, on_exit)
        return pane

    def get_live(self, pane_id: str) -> LivePane | None:
        return self._panes.get(pane_id)

    def list(self, *, workspace_id: str | None = None) -> list[TerminalPane]:
        values = [lp.pane for lp in self._panes.values()]
        if workspace_id:
            values = [p for p in values if p.workspace_id == workspace_id]
        return values

    def mark_exited(self, pane_id: str) -> None:
        live = self._panes.get(pane_id)
        if live:
            live.pane.status = "exited"

    def write(self, pane_id: str, data: bytes) -> bool:
        live = self._panes.get(pane_id)
        if live is None:
            return False
        terminal_service.write(live.proc, data)
        return True

    def resize(self, pane_id: str, rows: int, cols: int) -> bool:
        live = self._panes.get(pane_id)
        if live is None:
            return False
        terminal_service.resize(live.proc, rows, cols)
        return True

    def remove(self, pane_id: str) -> bool:
        live = self._panes.pop(pane_id, None)
        if live is None:
            return False
        terminal_service.kill(live.proc)
        return True

    def close_all(self) -> None:
        """Backend shutdown — kill every live pane so a dev-server reload or
        app quit doesn't leak shell/claude/codex processes the way the
        Tauri sidecar itself used to before its own SIGTERM fix."""
        for pane_id in list(self._panes.keys()):
            self.remove(pane_id)


_registry: TerminalRegistry | None = None


def get_terminal_registry() -> TerminalRegistry:
    global _registry
    if _registry is None:
        _registry = TerminalRegistry()
    return _registry
