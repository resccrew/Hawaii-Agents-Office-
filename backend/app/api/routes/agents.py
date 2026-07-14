"""Add-Agent flow (Phase 6): POST /api/v1/agents spawns a real, invisible
`claude -p` session and makes it appear as a character — no terminal is
ever shown to the user, everything happens through this endpoint + the
existing /ws/chat/{session_id} + ChatPanel.tsx.

Design: the spawned agent's OWN claude session_id is the StateMachine key
(so it gets a full observation/chat pipeline for free), and the agent's
role/name ride along on that same session's SESSION_START event — the
StateMachine's `lead` renders AS that agent directly (see
state_machine.py's _apply_session and models/agents.py's Lead.role/name).

Bugfix note: an earlier version also synthesized a SUBAGENT_START with
agent_id == session_id, making the agent appear a second time as a Dev
next to its own idle default Lead. Removed — one spawned agent is one
character now, not two.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.agent_registry import get_agent_registry
from app.core.agent_spawner import SpawnError, spawn_agent
from app.core.connection_manager import get_manager
from app.core.event_processor import get_processor

router = APIRouter()


class CreateAgentRequest(BaseModel):
    provider: str = "claude"
    department_id: str
    role: str  # matches a DevRole value: programmer|game_designer|artist|qa_tester|producer
    name: str
    initial_prompt: str
    # Optional sprite/skin override — a DevRole key (e.g. "artist") that sets
    # which character sprite the agent renders with, independently of `role`.
    # None means "derive sprite from role as usual".
    sprite: str | None = None


class CreateAgentResponse(BaseModel):
    agent_id: str
    session_id: str
    status: str
    first_response: str


@router.post("/agents", response_model=CreateAgentResponse)
async def create_agent(payload: CreateAgentRequest) -> CreateAgentResponse:
    try:
        agent, first_response = await spawn_agent(
            provider=payload.provider,
            department_id=payload.department_id,
            role=payload.role,
            name=payload.name,
            initial_prompt=payload.initial_prompt,
            sprite=payload.sprite,
        )
    except SpawnError as exc:
        status_code = 400 if exc.stage == "provider" else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return CreateAgentResponse(
        agent_id=agent.agent_id,
        session_id=agent.claude_session_id,
        status=agent.status,
        first_response=first_response,
    )


@router.get("/agents")
async def list_agents(department_id: str | None = None) -> list[dict]:
    registry = get_agent_registry()
    return [
        {
            "agentId": a.agent_id,
            "provider": a.provider,
            "departmentId": a.department_id,
            "role": a.role,
            "name": a.name,
            "status": a.status,
            "sessionId": a.claude_session_id,
            "lastError": a.last_error,
        }
        for a in registry.list(department_id=department_id)
    ]


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str) -> dict:
    registry = get_agent_registry()
    agent = registry.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    # No process to kill (see agent_registry.remove's docstring) — just drop
    # the live StateMachine, if any, so it stops appearing/broadcasting, then
    # drop the registry entry itself.
    if agent.claude_session_id:
        manager = get_manager()
        processor = get_processor(manager)
        await processor.remove_session(agent.claude_session_id)

    registry.remove(agent_id)
    return {"agentId": agent_id, "status": "deleted"}
