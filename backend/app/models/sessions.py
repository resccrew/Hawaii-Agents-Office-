from datetime import datetime
from typing import NotRequired, TypedDict, cast

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.models.agents import Dev, Lead, StudioState
from app.models.common import TodoItem

__all__ = [
    "ConversationEntry",
    "HistoryEntry",
    "Session",
    "GameState",
]


class ConversationEntry(TypedDict):
    """A single turn in the conversation history."""

    id: str
    role: str  # "user" | "assistant" | "thinking" | "tool"
    agentId: str
    text: str
    timestamp: str
    source: NotRequired[str]  # "interactive" | "chat" — see ChatEventData
    toolName: NotRequired[str]


class HistoryEntry(TypedDict):
    """A single entry in the event history log."""

    id: str
    type: str
    agentId: str
    summary: str
    timestamp: str
    detail: dict[str, object]


class Session(BaseModel):
    """A Claude Code session summary."""

    id: str
    created_at: datetime
    updated_at: datetime
    status: str  # "active" | "completed" | "error"
    event_count: int
    dev_count: int


class GameState(BaseModel):
    """Complete state of the studio visualization for frontend rendering."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    session_id: str
    lead: Lead
    devs: list[Dev]
    studio: StudioState
    last_updated: datetime
    history: list[HistoryEntry] = Field(default_factory=lambda: cast(list[HistoryEntry], []))
    todos: list[TodoItem] = Field(default_factory=lambda: cast(list[TodoItem], []))
    arrival_queue: list[str] = Field(default_factory=lambda: cast(list[str], []))
    departure_queue: list[str] = Field(default_factory=lambda: cast(list[str], []))
    conversation: list[ConversationEntry] = Field(
        default_factory=lambda: cast(list[ConversationEntry], [])
    )
    department_id: str | None = None
    room_id: str | None = None
