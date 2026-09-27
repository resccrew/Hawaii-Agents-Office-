"""Workspace registry — the project-tab concept (Phase 2 of the BridgeSpace
rework): each Workspace pairs a repo checkout with the department that owns
its agents/kanban board. Same in-memory-dict + best-effort JSON snapshot
pattern as agent_registry.py, so the tab strip survives a backend restart.

Deliberately does NOT duplicate git_ops.py's repo list/status/push — a
Workspace's repo_path is registered into git_ops (add_repo) on creation and
git_ops's own active-repo pointer is flipped (set_active) on activation, so
GitBar keeps working exactly as it already does, just now driven by whichever
workspace tab is active instead of its own independent selector.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.core import git_ops
from app.models.workspaces import Workspace

STATE_FILE = Path.home() / "studio-ops" / "state" / "workspaces.json"

# Matches ceo.py's CEO_DEPARTMENT — the pre-existing single-department world
# this seeds from, so an upgrade from before workspace tabs existed doesn't
# leave the human staring at an empty tab strip.
DEFAULT_DEPARTMENT = "Engineering"


@dataclass
class WorkspaceEntry:
    id: str
    name: str
    repo_path: str
    department_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_model(self) -> Workspace:
        return Workspace(
            id=self.id,
            name=self.name,
            repo_path=self.repo_path,
            department_id=self.department_id,
            created_at=self.created_at,
        )


class WorkspaceRegistry:
    def __init__(self) -> None:
        self._workspaces: dict[str, WorkspaceEntry] = {}
        self._active_id: str | None = None
        self._load()
        self._seed_from_git_ops()

    def create(self, *, name: str, repo_path: str, department_id: str) -> Workspace:
        resolved_path = Path(repo_path).expanduser().resolve()
        # Checked (and rejected) *before* the dict mutation below — this
        # used to call git_ops.add_repo() only after already inserting the
        # entry into self._workspaces, so a path outside the allowlist left
        # a half-registered workspace in memory even though the client got
        # a 400 and the on-disk snapshot was never written.
        if not git_ops.is_allowed_repo_path(resolved_path):
            raise ValueError(f"path is outside the allowed roots: {resolved_path}")
        resolved = str(resolved_path)
        if not git_ops.is_git_repo(resolved):
            raise ValueError(f"not a git repository: {resolved}")
        entry = WorkspaceEntry(
            id=f"workspace-{uuid.uuid4().hex[:10]}",
            name=name,
            repo_path=resolved,
            department_id=department_id,
        )
        self._workspaces[entry.id] = entry
        # Register with git_ops so GitBar's existing repo list/status/push
        # machinery sees this repo too — no separate tracking to keep in sync.
        git_ops.add_repo(resolved)
        if self._active_id is None:
            self._active_id = entry.id
        self.save()
        return entry.to_model()

    def get(self, workspace_id: str) -> Workspace | None:
        entry = self._workspaces.get(workspace_id)
        return entry.to_model() if entry else None

    def list(self) -> list[Workspace]:
        return [e.to_model() for e in sorted(self._workspaces.values(), key=lambda e: e.created_at)]

    def active_id(self) -> str | None:
        return self._active_id

    def activate(self, workspace_id: str) -> Workspace:
        entry = self._workspaces.get(workspace_id)
        if entry is None:
            raise ValueError(f"workspace not found: {workspace_id}")
        self._active_id = workspace_id
        # Flip git_ops's own active-repo pointer too, so GitBar reflects the
        # tab switch without needing its own workspace-awareness.
        git_ops.set_active(entry.repo_path)
        self.save()
        return entry.to_model()

    def remove(self, workspace_id: str) -> bool:
        existed = self._workspaces.pop(workspace_id, None) is not None
        if existed:
            if self._active_id == workspace_id:
                remaining = list(self._workspaces.values())
                self._active_id = remaining[0].id if remaining else None
            self.save()
        return existed

    def save(self) -> None:
        """Best-effort JSON snapshot — never raises, matching every other
        registry in this codebase (a disk hiccup can't break a create/activate
        that otherwise succeeded)."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "active_id": self._active_id,
                "workspaces": [
                    {**asdict(e), "created_at": e.created_at.isoformat()} for e in self._workspaces.values()
                ],
            }
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(STATE_FILE)
        except OSError:
            pass

    def _load(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            raw = json.loads(STATE_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for item in raw.get("workspaces", []):
            item = dict(item)
            item["created_at"] = datetime.fromisoformat(item["created_at"])
            entry = WorkspaceEntry(**item)
            self._workspaces[entry.id] = entry
        self._active_id = raw.get("active_id")

    def _seed_from_git_ops(self) -> None:
        """First run after upgrading to workspace tabs: if there are no
        workspaces yet but git_ops already has an active repo (the
        pre-workspace single-repo world), wrap it in one default Workspace
        instead of showing an empty tab strip."""
        if self._workspaces:
            return
        state = git_ops.list_state()
        active_repo = state.get("active")
        if not active_repo:
            return
        entry = WorkspaceEntry(
            id=f"workspace-{uuid.uuid4().hex[:10]}",
            name=Path(active_repo).name,
            repo_path=active_repo,
            department_id=DEFAULT_DEPARTMENT,
        )
        self._workspaces[entry.id] = entry
        self._active_id = entry.id
        self.save()


_registry: WorkspaceRegistry | None = None


def get_workspace_registry() -> WorkspaceRegistry:
    global _registry
    if _registry is None:
        _registry = WorkspaceRegistry()
    return _registry
