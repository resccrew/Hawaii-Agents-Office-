"""Agent + office memory endpoints. Thin REST wrapper over
app/core/memory_store.py — same shape as agents.py/tasks.py: a plain
router, Pydantic request models, memory_store's own exceptions mapped to
HTTP status codes here rather than inside the store (keeps memory_store
usable from the MCP tools and the store's own tests without any HTTP
concept leaking into it).

`scope` in every path is either the literal string "office" (the shared,
project-wide memory) or an agent_id (that agent's own memory, living
directly in its agent-workspaces/{agent_id}/ directory) — memory_store
validates and rejects anything else itself.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import memory_store as ms

router = APIRouter()


def _http_error(exc: ms.MemoryError) -> HTTPException:
    if isinstance(exc, ms.FactNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


class WriteMemoryRequest(BaseModel):
    name: str
    description: str
    type: str
    body: str


class MemoryIndexEntryOut(BaseModel):
    slug: str
    name: str
    description: str


class MemoryFactOut(BaseModel):
    scope: str
    slug: str
    name: str
    description: str
    type: str
    body: str
    updatedAt: str


def _to_fact_out(fact: ms.MemoryFact) -> MemoryFactOut:
    return MemoryFactOut(
        scope=fact.scope,
        slug=fact.slug,
        name=fact.name,
        description=fact.description,
        type=fact.type,
        body=fact.body,
        updatedAt=fact.updated_at,
    )


@router.get("/memory/{scope}", response_model=list[MemoryIndexEntryOut])
async def list_memory(scope: str) -> list[MemoryIndexEntryOut]:
    try:
        entries = ms.list_memory(scope)
    except ms.MemoryError as exc:
        raise _http_error(exc) from exc
    return [MemoryIndexEntryOut(slug=e.slug, name=e.name, description=e.description) for e in entries]


@router.get("/memory/{scope}/{slug}", response_model=MemoryFactOut)
async def read_memory(scope: str, slug: str) -> MemoryFactOut:
    try:
        fact = ms.read_memory(scope, slug)
    except ms.MemoryError as exc:
        raise _http_error(exc) from exc
    return _to_fact_out(fact)


@router.put("/memory/{scope}/{slug}", response_model=MemoryFactOut)
async def write_memory(scope: str, slug: str, payload: WriteMemoryRequest) -> MemoryFactOut:
    try:
        fact = ms.write_memory(
            scope, slug, name=payload.name, description=payload.description, type=payload.type, body=payload.body
        )
    except ms.MemoryError as exc:
        raise _http_error(exc) from exc
    return _to_fact_out(fact)


@router.delete("/memory/{scope}/{slug}")
async def delete_memory(scope: str, slug: str) -> dict:
    try:
        ms.delete_memory(scope, slug)
    except ms.MemoryError as exc:
        raise _http_error(exc) from exc
    return {"scope": scope, "slug": slug, "status": "deleted"}
