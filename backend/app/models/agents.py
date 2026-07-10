from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.models.common import BubbleContent

__all__ = [
    "DevState",
    "LeadState",
    "DevRole",
    "Dev",
    "Lead",
    "StandupState",
    "BuildState",
    "StudioState",
]


class DevState(StrEnum):
    """Visual states for dev characters (ported 1:1 from claude-office AgentState)."""

    ARRIVING = "arriving"
    REPORTING = "reporting"
    WALKING_TO_DESK = "walking_to_desk"
    WORKING = "working"
    THINKING = "thinking"
    WAITING_PERMISSION = "waiting_permission"
    COMPLETED = "completed"
    WAITING = "waiting"
    REPORTING_DONE = "reporting_done"
    LEAVING = "leaving"
    IN_ELEVATOR = "in_elevator"
    IDLE = "idle"


class LeadState(StrEnum):
    """Visual states for the lead/producer character (ported 1:1 from claude-office BossState)."""

    IDLE = "idle"
    PHONE_RINGING = "phone_ringing"
    ON_PHONE = "on_phone"
    RECEIVING = "receiving"
    WORKING = "working"
    DELEGATING = "delegating"
    WAITING_PERMISSION = "waiting_permission"
    REVIEWING = "reviewing"
    COMPLETING = "completing"


class DevRole(StrEnum):
    """Cosmetic role, derived from department mapping — does not affect state machine."""

    PROGRAMMER = "programmer"
    GAME_DESIGNER = "game_designer"
    ARTIST = "artist"
    QA_TESTER = "qa_tester"
    PRODUCER = "producer"


class Dev(BaseModel):
    """Represents a subagent ("dev") in the studio visualization."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    native_id: str | None = None
    name: str | None = None
    color: str
    number: int
    role: DevRole = DevRole.PROGRAMMER
    state: DevState
    desk: int | None = None
    bubble: BubbleContent | None = None
    current_task: str | None = None
    position: dict[str, int] = {"x": 0, "y": 0}
    character_type: str | None = None  # "lead" | "teammate" | "subagent"
    parent_session_id: str | None = None
    parent_id: str | None = None
    # studio-ops addition: whether this dev is currently reachable for chat
    # (mirrors StateMachine.interactive_turn_active, exposed for the frontend
    # chat-trigger affordance without a second round trip).
    chat_available: bool = True


class Lead(BaseModel):
    """Represents the main Claude session ("lead"/"producer") in the studio."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    state: LeadState
    current_task: str | None = None
    bubble: BubbleContent | None = None
    position: dict[str, int] = {"x": 640, "y": 830}
    chat_available: bool = True
    # Bugfix (Phase 6 double-render): when set, this Lead IS a spawned
    # peer agent (not a generic interactive session) — the frontend
    # renders it with that role's sprite and this name instead of the
    # default "Producer" capsule. None for real hook-observed sessions.
    role: DevRole | None = None
    name: str | None = None


class StandupState(StrEnum):
    """Visual states for the stand-up corner (renamed from ElevatorState)."""

    CLOSED = "closed"
    ARRIVING = "arriving"
    OPEN = "open"
    DEPARTING = "departing"


class BuildState(StrEnum):
    """Visual states for the build-status board (renamed from PhoneState)."""

    IDLE = "idle"
    RINGING = "ringing"
    IN_USE = "in_use"


class StudioState(BaseModel):
    """Represents the overall state of the studio environment (renamed from OfficeState)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    desk_count: int = 8
    standup_state: StandupState = StandupState.CLOSED
    build_state: BuildState = BuildState.IDLE
    context_utilization: float = 0.0
    tool_uses_since_compaction: int = 0
    print_report: bool = False
