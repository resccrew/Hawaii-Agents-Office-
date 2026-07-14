"""Per-session finite state machine.

Ported in spirit from claude-office's backend/app/core/state_machine.py:
same event-driven transition shape (Lead/Dev visual states), renamed to the
studio theme. One addition not present in the reference: `interactive_turn_active`,
a boolean derived purely from the existing hook event stream (set on
USER_PROMPT_SUBMIT/PRE_TOOL_USE without a matching STOP, cleared on STOP).
This is the signal the Phase 3 chat bridge reads before injecting a headless
turn into a session — see core/chat_bridge.py. It is a heuristic (see
compiled-dreaming-badger.md's Open Risks §4), not a hard guarantee.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.agents import Dev, DevRole, DevState, Lead, LeadState, StudioState
from app.models.events import (
    AgentEvent,
    AnyEvent,
    ChatEvent,
    EventType,
    LifecycleEvent,
    PromptEvent,
    SessionEvent,
    ToolEvent,
)
from app.models.sessions import ConversationEntry, GameState, HistoryEntry

# Event types that indicate the interactive terminal has an in-flight turn.
_TURN_START_EVENTS = {EventType.USER_PROMPT_SUBMIT, EventType.PRE_TOOL_USE}
# Event types that indicate the interactive terminal has gone idle again.
_TURN_END_EVENTS = {EventType.STOP, EventType.SESSION_END}


class StateMachine:
    """Owns the full visual + safety state for a single Claude Code session."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.lead = Lead(state=LeadState.IDLE)
        self.devs: dict[str, Dev] = {}
        self.studio = StudioState()
        self.history: list[HistoryEntry] = []
        self.conversation: list[ConversationEntry] = []
        self.department_id: str | None = None
        self.room_id: str | None = None
        self.last_updated = datetime.now(UTC)

        # Chat-safety gate (studio-ops addition, not in claude-office).
        self.interactive_turn_active: bool = False

        # Empirically required for Phase 3 chat: `claude -p --resume` is
        # tied to the cwd the session was created in — resuming from a
        # different cwd fails with "No conversation found with session ID".
        # Captured from the first event that carries it (hooks send
        # working_dir/project_dir on session_start and most other events).
        self.working_dir: str | None = None

        self._dev_counter = 0

    # -- event application ---------------------------------------------

    def apply(self, event: AnyEvent) -> None:
        self.last_updated = datetime.now(UTC)

        if event.data.working_dir:
            self.working_dir = event.data.working_dir
        elif event.data.project_dir and not self.working_dir:
            self.working_dir = event.data.project_dir

        if event.event_type in _TURN_START_EVENTS:
            self.interactive_turn_active = True
        elif event.event_type in _TURN_END_EVENTS:
            self.interactive_turn_active = False

        match event:
            case SessionEvent():
                self._apply_session(event)
            case ToolEvent():
                self._apply_tool(event)
            case PromptEvent():
                self._apply_prompt(event)
            case AgentEvent():
                self._apply_agent(event)
            case LifecycleEvent():
                self._apply_lifecycle(event)
            case ChatEvent():
                self._apply_chat(event)

        if event.data.department_id:
            self.department_id = event.data.department_id
        if event.data.room_id:
            self.room_id = event.data.room_id

        self._record_history(event)

    def _apply_session(self, event: SessionEvent) -> None:
        if event.event_type == EventType.SESSION_START:
            self.lead.state = LeadState.IDLE
            self.interactive_turn_active = False
            # Bugfix: a spawned peer agent's role/name (see agents.py) —
            # replaces the earlier synthesized-self-Dev hack.
            if event.data.agent_role:
                normalized = event.data.agent_role.lower().replace("-", "_")
                for role in DevRole:
                    if role.value == normalized:
                        self.lead.role = role
                        break
            if event.data.agent_name:
                self.lead.name = event.data.agent_name
            if event.data.summary:
                self.lead.current_task = event.data.summary
            # Sprite/skin override — stored as-is (a DevRole key string);
            # the frontend resolves it to a path via SPRITE_PATH_BY_ROLE.
            if event.data.agent_sprite:
                self.lead.sprite = event.data.agent_sprite
        elif event.event_type == EventType.SESSION_END:
            self.lead.state = LeadState.IDLE
            self.interactive_turn_active = False

    def _apply_tool(self, event: ToolEvent) -> None:
        target = self._resolve_actor(event.data.agent_id)
        if event.event_type == EventType.PRE_TOOL_USE:
            self._set_state(target, working=True)
        elif event.event_type == EventType.POST_TOOL_USE:
            if event.data.success is False:
                self._set_state(target, working=True)  # stay busy, error surfaces via bubble
            else:
                self._set_state(target, working=True)
        elif event.event_type == EventType.PERMISSION_REQUEST:
            self._set_state(target, waiting_permission=True)

    def _apply_prompt(self, event: PromptEvent) -> None:
        self.lead.state = LeadState.RECEIVING
        if event.data.prompt:
            self.conversation.append(
                ConversationEntry(
                    id=str(uuid.uuid4()),
                    role="user",
                    agentId="lead",
                    text=event.data.prompt,
                    timestamp=event.timestamp.isoformat(),
                    source="interactive",
                )
            )

    def _find_dev(self, agent_id: str | None, native_agent_id: str | None) -> Dev | None:
        """Resolve a dev by agent_id or native_agent_id, tolerating cross-field
        mismatch between SUBAGENT_START and SUBAGENT_STOP events.

        The bug: SUBAGENT_START may store the dev under ``agent_id`` (e.g. the
        tool-use id), but SUBAGENT_STOP sometimes only carries ``native_agent_id``
        (and vice-versa), causing the simple ``agent_id in self.devs`` check to
        miss the entry and leave the sprite stuck on screen.

        Strategy (fastest to slowest):
        1. Direct dict key lookup by agent_id.
        2. Direct dict key lookup by native_agent_id.
        3. Linear scan comparing dev.native_id (handles the case where START
           stored under agent_id but STOP only carries native_agent_id).
        4. Linear scan comparing dev.id (handles the reverse mismatch)."""
        if agent_id and agent_id in self.devs:
            return self.devs[agent_id]
        if native_agent_id and native_agent_id in self.devs:
            return self.devs[native_agent_id]
        for dev in self.devs.values():
            if native_agent_id and dev.native_id == native_agent_id:
                return dev
        for dev in self.devs.values():
            if agent_id and (dev.id == agent_id or dev.native_id == agent_id):
                return dev
        return None

    def _apply_agent(self, event: AgentEvent) -> None:
        agent_id = event.data.agent_id or event.data.native_agent_id
        if event.event_type == EventType.SUBAGENT_START and agent_id:
            self._dev_counter += 1
            self.devs[agent_id] = Dev(
                id=agent_id,
                native_id=event.data.native_agent_id,
                name=event.data.agent_name,
                color=_color_for_index(self._dev_counter),
                number=self._dev_counter,
                role=_role_for(event.data.agent_type, self._dev_counter),
                state=DevState.ARRIVING,
                current_task=event.data.task_description,
                parent_session_id=self.session_id,
            )
            self.lead.state = LeadState.DELEGATING
        elif event.event_type == EventType.SUBAGENT_STOP:
            # Use _find_dev instead of a plain dict lookup so the sprite is
            # correctly marked LEAVING even when SUBAGENT_STOP carries a
            # different id field than the one SUBAGENT_START used as key.
            dev = self._find_dev(event.data.agent_id, event.data.native_agent_id)
            if dev is not None:
                dev.state = DevState.LEAVING
                dev.current_task = event.data.result_summary
        elif event.event_type == EventType.AGENT_UPDATE and agent_id and agent_id in self.devs:
            if event.data.task_description:
                self.devs[agent_id].current_task = event.data.task_description
        elif event.event_type == EventType.CLEANUP and agent_id:
            self.devs.pop(agent_id, None)

    def _apply_lifecycle(self, event: LifecycleEvent) -> None:
        target = self._resolve_actor(event.data.agent_id)
        if event.event_type == EventType.STOP:
            self._set_state(target, idle=True)
        elif event.event_type == EventType.NOTIFICATION:
            self._set_state(target, waiting_permission=True)
        elif event.event_type == EventType.CONTEXT_COMPACTION:
            self.studio.tool_uses_since_compaction = 0
        elif event.event_type == EventType.WAITING:
            self._set_state(target, waiting=True)
        elif event.event_type == EventType.LEAVING and isinstance(target, Dev):
            target.state = DevState.LEAVING
        elif event.event_type == EventType.ERROR:
            pass  # surfaced via bubble content upstream; no state transition of record

    def _apply_chat(self, event: ChatEvent) -> None:
        """Chat-bridge turns are tagged source="chat" so the frontend/observation
        timeline can distinguish them from real interactive terminal activity
        (Phase 3, plan item: "Chat message attribution in the observation timeline").

        Also drives the office's busy/idle visual: a spawned agent has no hook
        stream (headless `claude -p`), so chat turns are the ONLY activity
        signal the room ever sees. The prompt half of a turn (chat_bridge
        _record(prompt=...)) flips the Lead to WORKING; the response half
        (_record(response_text=...)) flips it back to IDLE. Broadcast to
        overview happens for free — this event goes through EventProcessor."""
        if event.data.prompt:
            self.lead.state = LeadState.WORKING
        if event.data.response_text:
            self.lead.state = LeadState.IDLE
        if event.data.prompt:
            self.conversation.append(
                ConversationEntry(
                    id=str(uuid.uuid4()),
                    role="user",
                    agentId="lead",
                    text=event.data.prompt,
                    timestamp=event.timestamp.isoformat(),
                    source="chat",
                )
            )
        if event.data.response_text:
            self.conversation.append(
                ConversationEntry(
                    id=str(uuid.uuid4()),
                    role="assistant",
                    agentId="lead",
                    text=event.data.response_text,
                    timestamp=event.timestamp.isoformat(),
                    source="chat",
                )
            )

    # -- helpers ----------------------------------------------------------

    def _resolve_actor(self, agent_id: str | None) -> Lead | Dev:
        if agent_id and agent_id in self.devs:
            return self.devs[agent_id]
        return self.lead

    def _set_state(
        self,
        actor: Lead | Dev,
        *,
        working: bool = False,
        waiting_permission: bool = False,
        waiting: bool = False,
        idle: bool = False,
    ) -> None:
        if isinstance(actor, Lead):
            if working:
                actor.state = LeadState.WORKING
            elif waiting_permission:
                actor.state = LeadState.WAITING_PERMISSION
            elif idle:
                actor.state = LeadState.IDLE
        else:
            if working:
                actor.state = DevState.WORKING
            elif waiting_permission:
                actor.state = DevState.WAITING_PERMISSION
            elif waiting:
                actor.state = DevState.WAITING
            elif idle:
                actor.state = DevState.IDLE
            actor.chat_available = not self.interactive_turn_active
        if isinstance(actor, Lead):
            actor.chat_available = not self.interactive_turn_active

    def _record_history(self, event: AnyEvent) -> None:
        self.history.append(
            HistoryEntry(
                id=str(uuid.uuid4()),
                type=str(event.event_type),
                agentId=event.data.agent_id or "lead",
                summary=_summary_for(event),
                timestamp=event.timestamp.isoformat(),
                detail={},
            )
        )
        # Cap history to avoid unbounded growth in long-running sessions.
        if len(self.history) > 200:
            self.history = self.history[-200:]

    # -- snapshot -----------------------------------------------------------

    def snapshot(self) -> GameState:
        return GameState(
            session_id=self.session_id,
            lead=self.lead,
            devs=list(self.devs.values()),
            studio=self.studio,
            last_updated=self.last_updated,
            history=list(self.history),
            conversation=list(self.conversation),
            department_id=self.department_id,
            room_id=self.room_id,
        )


def _summary_for(event: AnyEvent) -> str:
    """A human-readable one-liner for the activity log. Most event types
    already carry `summary`/`message`; chat-bridge turns don't (they carry
    `prompt`/`response_text` instead — see ChatEventData), so without this
    special case every chat entry in the log just repeated its own type
    name ("chat_message") instead of showing what was actually said."""
    if isinstance(event, ChatEvent):
        text = event.data.prompt or event.data.response_text or ""
        prefix = "you: " if event.data.prompt else "reply: "
        text = text.strip().replace("\n", " ")
        if len(text) > 140:
            text = text[:140] + "…"
        return f"{prefix}{text}" if text else str(event.event_type)
    return event.data.summary or event.data.message or str(event.event_type)


_ROLE_CYCLE = [
    DevRole.PROGRAMMER,
    DevRole.GAME_DESIGNER,
    DevRole.ARTIST,
    DevRole.QA_TESTER,
]


def _role_for(agent_type: str | None, index: int) -> DevRole:
    """Cosmetic role assignment — purely visual, does not affect the state
    machine. Prefers a direct match on the hook's `agent_type` (e.g. a
    subagent literally named "qa-tester"); otherwise cycles through the
    roster so a session with several concurrent subagents reads visually
    distinct rather than identical programmer sprites."""
    if agent_type:
        normalized = agent_type.lower().replace("-", "_")
        for role in DevRole:
            if role.value == normalized:
                return role
    return _ROLE_CYCLE[(index - 1) % len(_ROLE_CYCLE)]


def _color_for_index(index: int) -> str:
    palette = [
        "#2563eb",
        "#db2777",
        "#059669",
        "#f59e0b",
        "#7c3aed",
        "#dc2626",
        "#0891b2",
        "#65a30d",
    ]
    return palette[(index - 1) % len(palette)]
