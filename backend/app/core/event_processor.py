"""Central event dispatch, ported from claude-office's event_processor.py.

Holds one StateMachine per session_id, applies incoming events to it, and
broadcasts the resulting snapshot over the session's WS channel plus the
overview channel. Department/room merge (`/ws/room/{id}`) reuses the same
snapshot, grouped by `department_id` on the state machine.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.core.connection_manager import ConnectionManager
from app.core.department_config import StudioConfig
from app.core.state_machine import StateMachine
from app.models.events import AnyEvent

PostProcessHook = Callable[[StateMachine], Awaitable[None]]


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
            self.state_machines[session_id] = StateMachine(session_id)
        return self.state_machines[session_id]

    async def process(self, event: AnyEvent) -> StateMachine:
        sm = self.get_or_create(event.session_id)

        if self.studio_config and event.data.project_name:
            dept = self.studio_config.department_for_repo(event.data.project_name)
            if dept:
                sm.department_id = dept.name

        sm.apply(event)

        snapshot = sm.snapshot()
        envelope = {
            "type": "state_update",
            "timestamp": snapshot.last_updated.isoformat(),
            "session_id": sm.session_id,
            "state": snapshot.model_dump(mode="json", by_alias=True),
        }
        await self.manager.broadcast_session(sm.session_id, envelope)
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
