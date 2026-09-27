#!/usr/bin/env python3
"""Studio Ops MCP server — Phase 6's agent-to-agent coordination surface.

Every Claude-provider agent spawned via POST /api/v1/agents gets this
server wired in via --mcp-config (see agent_registry.py workspace setup),
with STUDIO_OPS_AGENT_ID / STUDIO_OPS_AGENT_SESSION_ID env vars identifying
which agent is calling. Tools proxy to the already-running FastAPI backend
over HTTP rather than reimplementing any logic — `studio_send_message` in
particular goes through the exact same ChatBridge.enqueue_chat_message
best-effort queue a human's chat message would (POST /api/v1/chat/...),
so an agent-initiated message can't bypass the interactive_turn_active
safety gate from Phase 3.

Runs as its own subprocess over stdio — Claude Code (the MCP client) starts
it, this process is not part of the main uvicorn server.

Bugfix: every tool below is prefixed `studio_` (studio_list_agents,
studio_send_message, ...). Directly observed without the prefix: a spawned
agent asked to use "send_message" instead reasoned about Claude Code's own
built-in `SendMessage` tool (native Task-tool subagent messaging) and
refused, because the names were close enough for the model to conflate
them. The prefix makes the two unambiguous at the tool-name level instead
of relying on the prompt to disambiguate every time.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

BACKEND_URL = os.environ.get("STUDIO_OPS_BACKEND_URL", "http://localhost:8010")
CALLER_AGENT_ID = os.environ.get("STUDIO_OPS_AGENT_ID", "")
CALLER_SESSION_ID = os.environ.get("STUDIO_OPS_AGENT_SESSION_ID", "")

# Same token file app/core/auth.py's backend generates/reads — this process
# is a separate `python -m ... studio_ops_mcp` subprocess (started by Claude
# Code via --mcp-config, not part of the uvicorn process), so it needs its
# own read of the shared file rather than an in-process import.
_TOKEN_FILE = Path.home() / ".studio-ops" / "api-token"


def _auth_headers() -> dict[str, str]:
    try:
        token = _TOKEN_FILE.read_text().strip()
    except OSError:
        return {}
    return {"X-API-Key": token} if token else {}


mcp = FastMCP("studio-ops")


@mcp.tool()
async def studio_list_agents(department_id: str | None = None) -> list[dict]:
    """List agents currently registered in Studio Ops, optionally filtered
    to one department. Use this before studio_send_message to find a
    target agent's session_id."""
    async with httpx.AsyncClient(base_url=BACKEND_URL, headers=_auth_headers()) as client:
        params = {"department_id": department_id} if department_id else {}
        resp = await client.get("/api/v1/agents", params=params)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def studio_spawn_agent(
    department_id: str,
    role: str,
    name: str,
    initial_prompt: str,
    provider: str = "claude",
) -> dict:
    """Hire a new teammate — spawn another agent that appears in the office
    and can be chatted with, coordinated, and assigned tasks. Use this
    (as the CEO) to build out the team for a goal.

    role must be one of: programmer | game_designer | artist | qa_tester |
    producer. provider picks the teammate's underlying model — one of:
    claude (default; the only one with full studio-ops tool access, i.e.
    it can itself hire/message/manage tasks like you do) | openai | gemini
    | ollama (these three can chat and be coordinated via studio_send_message
    but cannot yet call studio_* tools themselves — hire them for
    plain execution work, not for sub-coordinating a team of their own).
    initial_prompt is the new agent's first briefing — be specific
    about what they should build or investigate. Returns the new agent's
    agent_id and session_id (use the session_id with studio_send_message and
    the agent_id with studio_update_task's assignee_agent_id). This call
    blocks until the new agent has finished its first turn, so it may take a
    few seconds."""
    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=300.0, headers=_auth_headers()) as client:
        resp = await client.post(
            "/api/v1/agents",
            json={
                "provider": provider,
                "department_id": department_id,
                "role": role,
                "name": name,
                "initial_prompt": initial_prompt,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "agent_id": data.get("agent_id"),
            "session_id": data.get("session_id"),
            "status": data.get("status"),
            "spawned_by": CALLER_AGENT_ID,
        }


@mcp.tool()
async def studio_send_message(target_session_id: str, message: str) -> dict:
    """Send a chat message to another agent (by its session_id, from
    studio_list_agents). This is a Studio Ops tool, NOT the same as the
    built-in SendMessage tool for Task-tool subagents — use this one for
    any target session_id obtained from studio_list_agents. Goes through
    the same best-effort queue as a human chat message — if the target is
    mid-turn, it queues and drains automatically once free rather than
    being dropped."""
    async with httpx.AsyncClient(base_url=BACKEND_URL, headers=_auth_headers()) as client:
        resp = await client.post(
            f"/api/v1/chat/{target_session_id}/messages", json={"text": message}
        )
        resp.raise_for_status()
        return {
            "status": resp.json().get("status", "unknown"),
            "from_agent_id": CALLER_AGENT_ID,
            "from_session_id": CALLER_SESSION_ID,
        }


@mcp.tool()
async def studio_list_tasks(department_id: str) -> list[dict]:
    """List the shared task board for a department."""
    async with httpx.AsyncClient(base_url=BACKEND_URL, headers=_auth_headers()) as client:
        resp = await client.get("/api/v1/tasks", params={"department_id": department_id})
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def studio_create_task(department_id: str, subject: str, description: str = "") -> dict:
    """Create a task on the shared board — visible to every agent and the
    human in that department, not just you."""
    async with httpx.AsyncClient(base_url=BACKEND_URL, headers=_auth_headers()) as client:
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "department_id": department_id,
                "subject": subject,
                "description": description or None,
                "created_by_agent_id": CALLER_AGENT_ID or None,
            },
        )
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def studio_update_task(
    task_id: str,
    status: str | None = None,
    assignee_agent_id: str | None = None,
    result: str | None = None,
) -> dict:
    """Update a shared task's status ("open"|"in_progress"|"done") and/or
    claim it by setting assignee_agent_id to your own agent id.

    When you set status="done", ALSO pass `result`: a short report of the
    outcome for the human to read — what you did, and a link or file path to
    the deliverable (e.g. "Built a playable snake game. File: /Users/.../
    index.html" or "Deployed at https://...". Include any caveats or test
    results). This is what shows up when the human clicks the completed task,
    so make it self-contained and specific."""
    payload: dict[str, str] = {}
    if status:
        payload["status"] = status
    if assignee_agent_id:
        payload["assignee_agent_id"] = assignee_agent_id
    if result:
        payload["result"] = result
    async with httpx.AsyncClient(base_url=BACKEND_URL, headers=_auth_headers()) as client:
        resp = await client.patch(f"/api/v1/tasks/{task_id}", json=payload)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def studio_generate_image(prompt: str) -> dict:
    """Ask the studio's image-generation agent (Nano-Banana-class
    provider) to generate an image from a prompt. Returns an error if no
    generative provider is configured — this is expected until an API key
    is set (STUDIO_OPS_NANOBANANA_API_KEY), not a bug."""
    async with httpx.AsyncClient(base_url=BACKEND_URL, headers=_auth_headers()) as client:
        resp = await client.post(
            "/api/v1/generate", json={"provider": "nanobanana", "kind": "image", "prompt": prompt}
        )
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
