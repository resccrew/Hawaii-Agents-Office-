"""Add-Agent flow (Phase 6): POST /api/v1/agents spawns a real, invisible
`claude -p` session and makes it appear as a Dev character — no terminal is
ever shown to the user, everything happens through this endpoint + the
existing /ws/chat/{session_id} + ChatPanel.tsx.

Key design choice: the spawned agent's OWN claude session_id doubles as
both the StateMachine key (so it gets a full observation/chat pipeline for
free) AND the Dev.id inside that same StateMachine (via a synthesized
SUBAGENT_START event, `agent_id=<that same session_id>`) — reusing
_apply_agent's existing subagent-creation path instead of adding a new
"peer agent" concept to the state machine. This is the one deliberate hack
in Phase 6: a session that is also, from its own state machine's point of
view, "its own subagent." It works because nothing in the Dev/StateMachine
model actually assumes agent_id != session_id; it's just an id string.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.agent_registry import get_agent_registry
from app.core.connection_manager import get_manager
from app.core.event_processor import get_processor
from app.models.events import (
    AgentEvent,
    AgentEventData,
    EventType,
    SessionEvent,
    SessionEventData,
)
from app.services.claude_cli_service import ClaudeCliError
from app.services.providers import get_conversational_provider

router = APIRouter()


class CreateAgentRequest(BaseModel):
    provider: str = "claude"
    department_id: str
    role: str  # matches a DevRole value: programmer|game_designer|artist|qa_tester|producer
    name: str
    initial_prompt: str


class CreateAgentResponse(BaseModel):
    agent_id: str
    session_id: str
    status: str
    first_response: str


@router.post("/agents", response_model=CreateAgentResponse)
async def create_agent(payload: CreateAgentRequest) -> CreateAgentResponse:
    provider = get_conversational_provider(payload.provider)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"unknown provider: {payload.provider}")

    registry = get_agent_registry()
    agent = registry.create(
        provider=payload.provider,
        department_id=payload.department_id,
        role=payload.role,
        name=payload.name,
    )

    try:
        spawn_result = await provider.spawn(
            workspace_dir=agent.workspace_dir,
            initial_prompt=payload.initial_prompt,
            mcp_config_path=agent.mcp_config_path,
        )
    except ClaudeCliError as exc:
        agent.status = "error"
        agent.last_error = str(exc)
        raise HTTPException(status_code=502, detail=f"failed to spawn agent: {exc}") from exc

    session_id = spawn_result.external_session_id
    if not session_id:
        agent.status = "error"
        agent.last_error = "provider did not return a resumable session id"
        raise HTTPException(status_code=502, detail=agent.last_error)

    agent.claude_session_id = session_id
    agent.status = "active"

    manager = get_manager()
    processor = get_processor(manager)
    now = datetime.now(UTC)

    # 1. SESSION_START — creates the StateMachine, records working_dir
    #    (needed for every future --resume call, same as any hook-observed
    #    session) and department_id.
    await processor.process(
        SessionEvent(
            event_type=EventType.SESSION_START,
            session_id=session_id,
            timestamp=now,
            data=SessionEventData(
                working_dir=agent.workspace_dir,
                department_id=payload.department_id,
                reason="spawned",
            ),
        )
    )

    # 2. SUBAGENT_START with agent_id == session_id — makes this session
    #    appear as a Dev inside its own StateMachine (see module docstring).
    await processor.process(
        AgentEvent(
            event_type=EventType.SUBAGENT_START,
            session_id=session_id,
            timestamp=now,
            data=AgentEventData(
                agent_id=session_id,
                agent_name=payload.name,
                agent_type=payload.role,
                task_description=payload.initial_prompt,
            ),
        )
    )

    return CreateAgentResponse(
        agent_id=agent.agent_id,
        session_id=session_id,
        status=agent.status,
        first_response=spawn_result.first_response,
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
        }
        for a in registry.list(department_id=department_id)
    ]
