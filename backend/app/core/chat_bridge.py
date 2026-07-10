"""Best-effort chat orchestration (Phase 3, the capability claude-office lacks).

Design (see compiled-dreaming-badger.md, "Chat safety: best-effort queue"):
before invoking the headless CLI, check the session's StateMachine
`interactive_turn_active` flag; if a turn is in flight, queue the message
instead of sending. A per-session asyncio.Lock ensures only one headless
call runs at a time for a given session. A filesystem lock file is added as
defense-in-depth against a second process (e.g. a second studio-ops
instance) racing the same session — this is a heuristic, not a proof: there
is a real window between the last observed Stop hook and the next unfired
PreToolUse that this cannot see.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.core.agent_registry import get_agent_registry
from app.core.connection_manager import ConnectionManager
from app.core.event_processor import EventProcessor
from app.core.state_machine import StateMachine
from app.models.events import ChatEvent, ChatEventData, EventType
from app.services.claude_cli_service import ClaudeCliError, send_headless_message

LOCK_DIR = Path.home() / ".claude" / "studio-ops-locks"


class ChatBridge:
    def __init__(self, manager: ConnectionManager, processor: EventProcessor) -> None:
        self.manager = manager
        self.processor = processor
        self._locks: dict[str, asyncio.Lock] = {}
        self._queues: dict[str, list[str]] = {}
        self._cwds: dict[str, str | None] = {}
        LOCK_DIR.mkdir(parents=True, exist_ok=True)

    async def _record(
        self, session_id: str, *, prompt: str | None = None, response_text: str | None = None
    ) -> None:
        """Feed a chat turn into the observation pipeline (state_machine's
        conversation log, tagged source="chat") so the studio scene and any
        connected /ws/{session_id} clients see chat activity too, distinct
        from interactive terminal activity."""
        event = ChatEvent(
            event_type=EventType.CHAT_MESSAGE,
            session_id=session_id,
            timestamp=datetime.now(UTC),
            data=ChatEventData(prompt=prompt, response_text=response_text),
        )
        await self.processor.process(event)

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    async def enqueue_chat_message(
        self, sm: StateMachine, text: str, *, cwd: str | None = None
    ) -> None:
        """Best-effort send: if the interactive terminal has a turn in
        flight, queue and return immediately; a drain happens next time
        this is called for the session (simple pull-based drain, adequate
        for the expected chat cadence of a human clicking a character)."""
        queue = self._queues.setdefault(sm.session_id, [])
        queue.append(text)
        # Empirically required (see claude_cli_service.py docstring):
        # `--resume` fails outside the session's original working directory.
        # Fall back to whatever StateMachine captured from hook events if
        # the caller didn't pass one explicitly. Resolved once here and
        # reused by every drain (including the auto-drain triggered by
        # maybe_drain_on_state_change) — passing the raw `cwd` param again
        # below would silently drop this resolution back to None.
        #
        # Bugfix (found while verifying the Bug 4 persistence fix): after a
        # backend restart, sm.working_dir is empty — StateMachine is rebuilt
        # fresh in-memory and nothing re-fires a SESSION_START to repopulate
        # it, even though the *agent* is still perfectly resumable (its
        # AgentRegistry entry, including workspace_dir, DID survive the
        # restart). Without this fallback, chat with a spawned agent broke
        # after every backend restart with "No conversation found" — the
        # exact cwd-mismatch failure mode this whole cwd-resolution dance
        # exists to avoid, just reintroduced by the restart itself.
        agent_for_cwd = get_agent_registry().find_by_claude_session(sm.session_id)
        resolved_cwd = cwd or sm.working_dir or (agent_for_cwd.workspace_dir if agent_for_cwd else None)
        self._cwds[sm.session_id] = resolved_cwd

        if sm.interactive_turn_active:
            await self.manager.broadcast_chat(
                sm.session_id,
                {"type": "chat_queued", "text": text, "reason": "interactive_turn_active"},
            )
            return

        await self._drain(sm, cwd=resolved_cwd)

    async def maybe_drain_on_state_change(self, sm: StateMachine) -> None:
        """EventProcessor post-hook: called after every event is applied to
        any session. Drains this session's pending chat queue the moment
        interactive_turn_active clears (e.g. on Stop), instead of waiting
        for the next chat send to notice. Cheap no-op for sessions with an
        empty queue or still-active interactive turn."""
        if sm.interactive_turn_active:
            return
        if not self._queues.get(sm.session_id):
            return
        await self._drain(sm, cwd=self._cwds.get(sm.session_id))

    async def _drain(self, sm: StateMachine, *, cwd: str | None) -> None:
        lock = self._lock_for(sm.session_id)
        if lock.locked():
            return  # another drain already in flight for this session

        async with lock:
            queue = self._queues.setdefault(sm.session_id, [])
            while queue and not sm.interactive_turn_active:
                text = queue.pop(0)
                await self._send_one(sm, text, cwd=cwd)

    async def _send_one(self, sm: StateMachine, text: str, *, cwd: str | None) -> None:
        lock_file = LOCK_DIR / f"{sm.session_id}.lock"
        try:
            lock_file.touch(exist_ok=True)
        except OSError:
            pass  # best-effort defense-in-depth only; never block chat on this

        turn_id = str(uuid.uuid4())
        await self.manager.broadcast_chat(
            sm.session_id, {"type": "chat_turn_started", "turn_id": turn_id, "text": text}
        )
        await self._record(sm.session_id, prompt=text)

        # Phase 6: if this session belongs to a spawned agent (not just a
        # hook-observed interactive one), keep its studio-ops MCP tools
        # (send_message, create_task, ...) available on every turn — each
        # `claude -p` call is a fresh process with no memory of earlier
        # flags, so this must be re-passed every time, not just at spawn.
        agent = get_agent_registry().find_by_claude_session(sm.session_id)
        mcp_config_path = agent.mcp_config_path if agent else None
        # bypassPermissions only for sessions we spawned ourselves (isolated
        # agent-workspaces/ dir) — never for a real hook-observed interactive
        # session, where bypassing permissions on the user's own project
        # would be a genuine safety regression, not a convenience.
        permission_mode = "bypassPermissions" if agent else None

        response_text = ""
        try:
            async for chunk in send_headless_message(
                sm.session_id,
                text,
                cwd=cwd,
                mcp_config_path=mcp_config_path,
                permission_mode=permission_mode,
            ):
                if chunk.kind == "text_delta":
                    response_text = chunk.text
                    await self.manager.broadcast_chat(
                        sm.session_id,
                        {"type": "chat_delta", "turn_id": turn_id, "text": chunk.text},
                    )
                elif chunk.kind == "error":
                    await self.manager.broadcast_chat(
                        sm.session_id,
                        {"type": "chat_error", "turn_id": turn_id, "message": chunk.text},
                    )
                    return
        except ClaudeCliError as exc:
            await self.manager.broadcast_chat(
                sm.session_id, {"type": "chat_error", "turn_id": turn_id, "message": str(exc)}
            )
            return
        finally:
            try:
                lock_file.unlink(missing_ok=True)
            except OSError:
                pass

        await self.manager.broadcast_chat(
            sm.session_id,
            {"type": "chat_turn_complete", "turn_id": turn_id, "text": response_text},
        )
        await self._record(sm.session_id, response_text=response_text)


_bridge: ChatBridge | None = None


def get_chat_bridge(manager: ConnectionManager, processor: EventProcessor) -> ChatBridge:
    global _bridge
    if _bridge is None:
        _bridge = ChatBridge(manager, processor)
        processor.register_post_hook(_bridge.maybe_drain_on_state_change)
    return _bridge
