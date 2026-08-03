from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

__all__ = ["Workspace"]


class Workspace(BaseModel):
    """A project tab: a repo checkout paired with the department that owns
    its agents/kanban board. One Workspace = one repo_path + one
    department_id, created together — SidePanel/TaskBoard/GitBar are already
    all department_id-scoped, so switching the active workspace swaps the
    whole office/board/roster in one action.

    repo_path doubles as a git_ops.py repo: creating a Workspace registers
    it there too (git_ops.add_repo), and activating a Workspace flips
    git_ops's own active-repo pointer (git_ops.set_active) — reusing that
    already-working mechanism instead of standing up a second, parallel
    "what's the active repo" concept.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    name: str
    repo_path: str
    department_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
