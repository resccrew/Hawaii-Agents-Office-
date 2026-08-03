from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

__all__ = ["TerminalPane"]

TerminalKind = Literal["shell", "claude", "codex"]
TerminalStatus = Literal["running", "exited"]


class TerminalPane(BaseModel):
    """Metadata for one PTY-backed terminal pane. Deliberately doesn't carry
    the live PtyProcess (pid/fd) — that's core/terminal_registry.py's
    in-memory-only concern, never serialized to the frontend or persisted."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    workspace_id: str
    kind: TerminalKind
    status: TerminalStatus = "running"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
