from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

__all__ = [
    "ChatTurnStatus",
    "ChatMessage",
    "ChatSession",
]


class ChatTurnStatus(StrEnum):
    """Lifecycle of a single chat turn sent through the chat bridge."""

    QUEUED = "queued"
    STREAMING = "streaming"
    COMPLETED = "completed"
    ERROR = "error"


class ChatMessage(BaseModel):
    """A single message in a session's chat history."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    session_id: str
    role: str  # "user" | "assistant"
    text: str
    status: ChatTurnStatus = ChatTurnStatus.COMPLETED
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChatSession(BaseModel):
    """Per-session chat bridge bookkeeping."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    session_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    pending_queue: list[str] = Field(default_factory=list)  # queued user texts, FIFO
    turn_in_flight: bool = False
