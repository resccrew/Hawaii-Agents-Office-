import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
)

from app.models.common import BubbleContent, SpeechContent

__all__ = [
    "EventType",
    "EventDataBase",
    "SessionEventData",
    "ToolEventData",
    "PromptEventData",
    "AgentEventData",
    "LifecycleEventData",
    "TaskEventData",
    "BackgroundTaskEventData",
    "_EventBase",
    "SessionEvent",
    "ToolEvent",
    "PromptEvent",
    "AgentEvent",
    "LifecycleEvent",
    "TaskEvent",
    "BackgroundTaskEvent",
    "ChatEvent",
    "ChatEventData",
    "AnyEvent",
    "EventAdapter",
]


class EventType(StrEnum):
    """Types of events sent from Claude Code hooks (and the chat bridge)."""

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    PERMISSION_REQUEST = "permission_request"
    NOTIFICATION = "notification"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_INFO = "subagent_info"
    SUBAGENT_STOP = "subagent_stop"
    AGENT_UPDATE = "agent_update"
    STOP = "stop"
    CLEANUP = "cleanup"
    CONTEXT_COMPACTION = "context_compaction"
    REPORTING = "reporting"
    WALKING_TO_DESK = "walking_to_desk"
    WAITING = "waiting"
    LEAVING = "leaving"
    ERROR = "error"
    BACKGROUND_TASK_NOTIFICATION = "background_task_notification"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    TEAMMATE_IDLE = "teammate_idle"
    # studio-ops addition: chat-bridge turns, distinguished from interactive
    # hook-driven prompts so the observation timeline can tell them apart.
    CHAT_MESSAGE = "chat_message"


# ---------------------------------------------------------------------------
# Discriminated-union event layer (ported from claude-office ARC-014 design).
#
# Payload is split into one base + family-specific classes, grouped by which
# EventType values access them. Wire format is a flat JSON object; producers
# (hooks, chat bridge, fixtures) emit the same shape regardless of family.
# `extra="ignore"` everywhere: hooks send fields opportunistically.
# ---------------------------------------------------------------------------


class EventDataBase(BaseModel):
    """Fields every event may carry."""

    model_config = ConfigDict(extra="ignore")

    project_name: str | None = None
    project_dir: str | None = None
    working_dir: str | None = None
    agent_id: str | None = None
    native_agent_id: str | None = None
    transcript_path: str | None = None
    agent_transcript_path: str | None = None
    summary: str | None = None
    message: str | None = None
    team_name: str | None = None
    teammate_name: str | None = None
    task_list_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    department_id: str | None = None
    room_id: str | None = None


class SessionEventData(EventDataBase):
    """Payload for SESSION_START, SESSION_END."""

    reason: str | None = None
    # Phase 6 bugfix: a spawned agent's SESSION_START carries its own role
    # and display name, so the StateMachine's Lead can render as that agent
    # directly instead of the earlier "SUBAGENT_START with agent_id ==
    # session_id" hack (which produced a redundant idle Lead + real Dev).
    agent_role: str | None = None
    agent_name: str | None = None
    # Optional sprite/skin key (a DevRole value) — overrides the role-derived
    # sprite so an agent can have any character appearance regardless of its
    # functional role. None means "use role's default sprite".
    agent_sprite: str | None = None


class ToolEventData(EventDataBase):
    """Payload for PRE_TOOL_USE, POST_TOOL_USE, PERMISSION_REQUEST."""

    tool_name: str | None = None
    tool_use_id: str | None = None
    tool_input: dict[str, Any] | None = None
    success: bool | None = None
    result_summary: str | None = None
    error_type: str | None = None
    thinking: str | None = None


class PromptEventData(EventDataBase):
    """Payload for USER_PROMPT_SUBMIT."""

    prompt: str | None = None


class AgentEventData(EventDataBase):
    """Payload for SUBAGENT_START, SUBAGENT_INFO, SUBAGENT_STOP, AGENT_UPDATE, CLEANUP."""

    agent_name: str | None = None
    agent_type: str | None = None
    task_description: str | None = None
    result_summary: str | None = None
    tool_use_id: str | None = None
    thinking: str | None = None
    success: bool | None = None
    bubble_content: BubbleContent | None = None
    speech_content: SpeechContent | None = None


class LifecycleEventData(EventDataBase):
    """Payload for STOP, NOTIFICATION, CONTEXT_COMPACTION, REPORTING,
    WALKING_TO_DESK, WAITING, LEAVING, ERROR, TEAMMATE_IDLE."""

    notification_type: str | None = None
    error_type: str | None = None
    reason: str | None = None
    bubble_content: BubbleContent | None = None
    speech_content: SpeechContent | None = None


class TaskEventData(EventDataBase):
    """Payload for TASK_CREATED, TASK_COMPLETED."""

    task_id: str | None = None
    task_subject: str | None = None


class BackgroundTaskEventData(EventDataBase):
    """Payload for BACKGROUND_TASK_NOTIFICATION."""

    background_task_id: str | None = None
    background_task_output_file: str | None = None
    background_task_status: str | None = None  # "completed" | "failed"
    background_task_summary: str | None = None


class ChatEventData(EventDataBase):
    """Payload for CHAT_MESSAGE — a turn originated by the chat bridge
    (headless `claude -p --resume`) rather than the interactive terminal."""

    prompt: str | None = None
    response_text: str | None = None
    turn_status: str | None = None  # "queued" | "streaming" | "completed" | "error"


class _EventBase(BaseModel):
    """Common envelope fields for every discriminated-union variant."""

    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", v):
            raise ValueError("session_id must be alphanumeric/dash/underscore, max 128 chars")
        return v


class SessionEvent(_EventBase):
    event_type: Literal[EventType.SESSION_START, EventType.SESSION_END]
    data: SessionEventData


class ToolEvent(_EventBase):
    event_type: Literal[
        EventType.PRE_TOOL_USE,
        EventType.POST_TOOL_USE,
        EventType.PERMISSION_REQUEST,
    ]
    data: ToolEventData


class PromptEvent(_EventBase):
    event_type: Literal[EventType.USER_PROMPT_SUBMIT]
    data: PromptEventData


class AgentEvent(_EventBase):
    event_type: Literal[
        EventType.SUBAGENT_START,
        EventType.SUBAGENT_INFO,
        EventType.SUBAGENT_STOP,
        EventType.AGENT_UPDATE,
        EventType.CLEANUP,
    ]
    data: AgentEventData


class LifecycleEvent(_EventBase):
    event_type: Literal[
        EventType.STOP,
        EventType.NOTIFICATION,
        EventType.CONTEXT_COMPACTION,
        EventType.REPORTING,
        EventType.WALKING_TO_DESK,
        EventType.WAITING,
        EventType.LEAVING,
        EventType.ERROR,
        EventType.TEAMMATE_IDLE,
    ]
    data: LifecycleEventData


class TaskEvent(_EventBase):
    event_type: Literal[EventType.TASK_CREATED, EventType.TASK_COMPLETED]
    data: TaskEventData


class BackgroundTaskEvent(_EventBase):
    event_type: Literal[EventType.BACKGROUND_TASK_NOTIFICATION]
    data: BackgroundTaskEventData


class ChatEvent(_EventBase):
    event_type: Literal[EventType.CHAT_MESSAGE]
    data: ChatEventData


AnyEvent = Annotated[
    SessionEvent
    | ToolEvent
    | PromptEvent
    | AgentEvent
    | LifecycleEvent
    | TaskEvent
    | BackgroundTaskEvent
    | ChatEvent,
    Field(discriminator="event_type"),
]

EventAdapter: TypeAdapter[AnyEvent] = TypeAdapter(AnyEvent)
