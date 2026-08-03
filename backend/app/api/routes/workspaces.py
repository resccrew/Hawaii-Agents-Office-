"""Workspace tab endpoints (Phase 2 of the BridgeSpace rework). Each
Workspace pairs a repo checkout with a department — the tab strip above the
main content area lets the human switch which project's kanban/roster/repo
they're looking at."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.core.workspace_registry import get_workspace_registry
from app.models.workspaces import Workspace

router = APIRouter()


class CreateWorkspaceRequest(BaseModel):
    name: str
    repo_path: str
    department_id: str | None = None  # defaults to `name` if unset


class WorkspaceListResponse(BaseModel):
    # Matches Workspace's camelCase-over-the-wire convention — the frontend
    # store reads `activeId`, not `active_id` (bugfix: this model originally
    # had no alias config, so the field silently went over the wire as
    # snake_case and every workspace-switch appeared to do nothing).
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    active_id: str | None
    workspaces: list[Workspace]


@router.get("/workspaces", response_model=WorkspaceListResponse)
async def list_workspaces() -> WorkspaceListResponse:
    registry = get_workspace_registry()
    return WorkspaceListResponse(active_id=registry.active_id(), workspaces=registry.list())


@router.post("/workspaces", response_model=Workspace)
async def create_workspace(payload: CreateWorkspaceRequest) -> Workspace:
    registry = get_workspace_registry()
    try:
        return registry.create(
            name=payload.name,
            repo_path=payload.repo_path,
            department_id=payload.department_id or payload.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/activate", response_model=Workspace)
async def activate_workspace(workspace_id: str) -> Workspace:
    registry = get_workspace_registry()
    try:
        return registry.activate(workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str) -> dict:
    registry = get_workspace_registry()
    if not registry.remove(workspace_id):
        raise HTTPException(status_code=404, detail="workspace not found")
    return {"workspaceId": workspace_id, "status": "deleted"}
