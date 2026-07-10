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

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.agent_registry import get_agent_registry
from app.core.connection_manager import get_manager
from app.core.event_processor import get_processor
from app.models.events import EventType, SessionEvent, SessionEventData
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
        # bypassPermissions is safe here specifically because this agent
        # runs in its own isolated agent-workspaces/<id>/ directory, never
        # the user's real projects — see claude_cli_service.py's module
        # docstring for why this is NOT done for hook-observed interactive
        # sessions (chat_bridge.py only sets this for registry-known agents).
        spawn_result = await provider.spawn(
            workspace_dir=agent.workspace_dir,
            initial_prompt=payload.initial_prompt,
            mcp_config_path=agent.mcp_config_path,
            permission_mode="bypassPermissions",
        )
    except ClaudeCliError as exc:
        agent.status = "error"
        agent.last_error = str(exc)
        registry.save()
        raise HTTPException(status_code=502, detail=f"failed to spawn agent: {exc}") from exc

    session_id = spawn_result.external_session_id
    if not session_id:
        agent.status = "error"
        agent.last_error = "provider did not return a resumable session id"
        registry.save()
        raise HTTPException(status_code=502, detail=agent.last_error)

    agent.claude_session_id = session_id
    agent.status = "active"
    registry.save()

    manager = get_manager()
    processor = get_processor(manager)

    # SESSION_START — creates the StateMachine, records working_dir (needed
    # for every future --resume call, same as any hook-observed session),
    # department_id, and this agent's role/name/task so its Lead renders as
    # the spawned character directly (see module docstring).
    await processor.process(
        SessionEvent(
            event_type=EventType.SESSION_START,
            session_id=session_id,
            timestamp=datetime.now(UTC),
            data=SessionEventData(
                working_dir=agent.workspace_dir,
                department_id=payload.department_id,
                reason="spawned",
                agent_role=payload.role,
                agent_name=payload.name,
                summary=payload.initial_prompt,
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
