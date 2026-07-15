"""Git endpoints — power the git bar under the office: list/select working
repositories and push the active one to GitHub with one click.

Git operations shell out to subprocess (blocking), so each is run in a thread
via asyncio.to_thread to avoid stalling the event loop.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import git_ops

router = APIRouter()


class AddRepoRequest(BaseModel):
    path: str


class SetActiveRequest(BaseModel):
    path: str


class PushRequest(BaseModel):
    message: str | None = None


class ConnectRequest(BaseModel):
    token: str


class SelectGithubRequest(BaseModel):
    full_name: str
    clone_url: str | None = None


@router.get("/git")
async def get_git_state() -> dict:
    return await asyncio.to_thread(git_ops.list_state)


@router.post("/git/repos")
async def add_repo(payload: AddRepoRequest) -> dict:
    try:
        return await asyncio.to_thread(git_ops.add_repo, payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/git/repos")
async def remove_repo(path: str) -> dict:
    return await asyncio.to_thread(git_ops.remove_repo, path)


@router.post("/git/active")
async def set_active(payload: SetActiveRequest) -> dict:
    try:
        return await asyncio.to_thread(git_ops.set_active, payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/git/push")
async def push(payload: PushRequest) -> dict:
    return await asyncio.to_thread(git_ops.push, payload.message)


@router.get("/git/github")
async def github(refresh: bool = True) -> dict:
    """Account status + the full list of repositories the connected GitHub
    account can access (empty until a token is set)."""
    status = await git_ops.github_status()
    repos = await git_ops.list_github_repos() if status.get("connected") else []
    return {"status": status, "repos": repos}


@router.post("/git/github/connect")
async def github_connect(payload: ConnectRequest) -> dict:
    from app.core.settings_store import get_settings_store

    get_settings_store().set_many({"github_token": payload.token.strip()})
    return await git_ops.github_status()


@router.post("/git/github/select")
async def github_select(payload: SelectGithubRequest) -> dict:
    try:
        return await git_ops.select_github_repo(payload.full_name, payload.clone_url)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
