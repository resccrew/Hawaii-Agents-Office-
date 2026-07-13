"""Central event dispatch, ported from claude-office's event_processor.py.

Holds one StateMachine per session_id, applies incoming events to it, and
broadcasts the resulting snapshot over the session's WS channel plus the
overview channel. Department/room merge (`/ws/room/{id}`) reuses the same
snapshot, grouped by `department_id` on the state machine.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.core.agent_registry import get_agent_registry
from app.core.connection_manager import ConnectionManager
from app.core.conversation_store import get_conversation_store
from app.core.department_config import StudioConfig
from app.core.state_machine import StateMachine
from app.models.events import AnyEvent, ChatEvent

PostProcessHook = Callable[[StateMachine], Awaitable[None]]


def is_registered_agent(session_id: str) -> bool:
    """The studio office (/ws/overview) shows only agents that actually
    exist in the registry — the ones spawned via "+ agent" or by the CEO.
    Hook-observed Claude Code sessions (from POST /api/v1/events) still get
    their own state machine + per-session channel, but they are NOT real
    studio agents and must not appear as phantom "Producer" sprites in the
    office. This is the single gate that keeps the two worlds separate."""
    return get_agent_registry().find_by_claude_session(session_id) is not None


class EventProcessor:
    def __init__(self, manager: ConnectionManager, studio_config: StudioConfig | None = None) -> None:
        self.manager = manager
        self.studio_config = studio_config
        self.state_machines: dict[str, StateMachine] = {}
        # Lets ChatBridge drain its best-effort queue the moment
        # interactive_turn_active clears (e.g. on Stop), instead of only on
        # the next chat send — see chat_bridge.py's registration.
        self._post_hooks: list[PostProcessHook] = []

    def register_post_hook(self, hook: PostProcessHook) -> None:
        self._post_hooks.append(hook)

    def get_or_create(self, session_id: str) -> StateMachine:
        if session_id not in self.state_machines:
            sm = StateMachine(session_id)
            # Rehydrate conversation history from disk — this StateMachine
            # is brand new (first time this session_id is seen since the
            # process started), so without this a backend restart mid-chat
            # would otherwise present as "the agent's replies vanished".
            sm.conversation = get_conversation_store().get(session_id)
            self.state_machines[session_id] = sm
        return self.state_machines[session_id]

    async def remove_session(self, session_id: str) -> StateMachine | None:
        """Drops a session's live StateMachine (used by DELETE /agents/{id})
        and tells anyone watching it — the session channel itself, overview,
        and its department's room — so it disappears from every screen
        instead of just going silent. Returns the removed machine (or None
        if it wasn't live) so the caller can tell whether there was anything
        to announce."""
        sm = self.state_machines.pop(session_id, None)
        if sm is None:
            return None

        envelope = {
            "type": "session_deleted",
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": session_id,
        }
        await self.manager.broadcast_session(session_id, envelope)
        await self.manager.broadcast_overview(envelope)
        if sm.department_id:
            await self.manager.broadcast_room(sm.department_id, envelope)

        return sm

    async def process(self, event: AnyEvent) -> StateMachine:
        sm = self.get_or_create(event.session_id)

        if self.studio_config and event.data.project_name:
            dept = self.studio_config.department_for_repo(event.data.project_name)
            if dept:
                sm.department_id = dept.name

        sm.apply(event)

        if isinstance(event, ChatEvent):
            # Persist immediately (not batched) — a chat turn is exactly two
            # of these per turn (prompt, then response), so this is cheap,
            # and immediacy matters: this IS the fix for restart-induced
            # message loss, so it must hit disk before anything can wipe it.
            get_conversation_store().sync(sm.session_id, sm.conversation)

        snapshot = sm.snapshot()
        envelope = {
            "type": "state_update",
            "timestamp": snapshot.last_updated.isoformat(),
            "session_id": sm.session_id,
            "state": snapshot.model_dump(mode="json", by_alias=True),
        }
        await self.manager.broadcast_session(sm.session_id, envelope)
        # Overview = the studio office, registry-backed agents only.
        if is_registered_agent(sm.session_id):
            await self.manager.broadcast_overview(envelope)
        if sm.department_id:
            await self.manager.broadcast_room(sm.department_id, envelope)

        for hook in self._post_hooks:
            await hook(sm)

        return sm


_processor: EventProcessor | None = None


def get_processor(manager: ConnectionManager, studio_config: StudioConfig | None = None) -> EventProcessor:
    global _processor
    if _processor is None:
        _processor = EventProcessor(manager, studio_config)
    return _processor
