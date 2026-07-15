from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

__all__ = ["TaskStatus", "SharedTask"]


class TaskStatus(StrEnum):
    """Status of a shared task board item."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class SharedTask(BaseModel):
    """A task on the department's shared board — the "shared context and
    shared tasks" coordination layer from Phase 6. Any agent (via the
    studio-ops MCP server's create_task/update_task tools) or the human
    (via the TaskBoard UI panel) can create/claim/complete these; they are
    the structured half of coordination, complementary to direct
    agent-to-agent chat via send_message."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    department_id: str
    subject: str
    description: str | None = None
    status: TaskStatus = TaskStatus.OPEN
    assignee_agent_id: str | None = None
    created_by_agent_id: str | None = None  # None = created by the human via UI
    # The outcome the assignee reports on completion — a short report, a
    # summary of what was done, and/or a link/file path to the deliverable.
    # Surfaced in the UI when the human clicks a done task. None until set.
    result: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
