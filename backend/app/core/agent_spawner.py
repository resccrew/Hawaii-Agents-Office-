"""Shared agent-spawn pipeline — the single implementation of "register an
agent, start its invisible `claude -p` session, and make it appear as a
character" used by BOTH the POST /api/v1/agents route (human clicks "+
agent") and the auto-started CEO (app/core/ceo.py). Previously this lived
inline in the route only; the CEO and the `studio_spawn_agent` MCP tool
(which lets the CEO spawn teammates) need the exact same flow, so it's
factored out here to avoid three divergent copies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.core.agent_registry import AgentSession, get_agent_registry
from app.core.connection_manager import get_manager
from app.core.event_processor import get_processor
from app.models.events import EventType, SessionEvent, SessionEventData
from app.services.providers import get_conversational_provider
from app.services.providers.base import ProviderError

# Written into every claude-provider agent's workspace before its first
# turn — Claude Code reads CLAUDE.md from its cwd automatically, so this is
# the one place the memory discipline needs to be stated for it to apply
# to every future turn (not just the initial_prompt, which the agent won't
# see again once it scrolls out of context). Other providers (openai/
# gemini/ollama) don't have an equivalent cwd-file convention, so this is
# claude-only — see the provider gate in spawn_agent() below.
MEMORY_INSTRUCTIONS = """# Memory

You have a persistent memory at `studio_memory_*` MCP tools (studio_memory_list,
studio_memory_read, studio_memory_write) — two scopes: your OWN agent memory
(the default, omit `scope`) and the shared office memory (`scope="office"`,
readable/writable by every agent, for project-wide facts and decisions).

- At the START of any task: call `studio_memory_list()` (your own memory)
  and `studio_memory_list(scope="office")` (shared) to see what's already
  known before you start. Read anything that looks relevant with
  `studio_memory_read`.
- At the END of a task: call `studio_memory_write` to record what you
  learned or decided — only what's non-obvious, would surprise a future
  reader, or took real effort to find out. Use `scope="office"` for
  anything a teammate should also know; leave scope unset for your own
  private progress notes.
"""


def _write_memory_instructions(workspace_dir: str) -> None:
    Path(workspace_dir, "CLAUDE.md").write_text(MEMORY_INSTRUCTIONS, encoding="utf-8")


async def _emit_session_start(agent: AgentSession) -> None:
    """Emit a SESSION_START for an agent so its Lead renders in the office.
    Shared by spawn (fresh agent) and rehydrate (existing agent after a
    restart)."""
    manager = get_manager()
    processor = get_processor(manager)
    await processor.process(
        SessionEvent(
            event_type=EventType.SESSION_START,
            session_id=agent.claude_session_id,
            timestamp=datetime.now(UTC),
            data=SessionEventData(
                working_dir=agent.workspace_dir,
                department_id=agent.department_id,
                reason="spawned",
                agent_role=agent.role,
                agent_name=agent.name,
                agent_sprite=agent.sprite,
            ),
        )
    )


async def rehydrate_office() -> None:
    """On startup, re-create an in-memory StateMachine for every registered
    agent that has a live session, so the office shows exactly the agents
    that actually exist — the registry is the persistent source of truth,
    but StateMachines are in-memory and would otherwise be empty after a
    restart (agents present in the roster, invisible in the room)."""
    registry = get_agent_registry()
    for agent in registry.list():
        if agent.claude_session_id and agent.status != "error":
            await _emit_session_start(agent)


class SpawnError(Exception):
    """Raised when an agent can't be spawned. `.stage` distinguishes a bad
    request (unknown provider) from a runtime failure (claude subprocess
    died) so callers can map to the right HTTP status."""

    def __init__(self, message: str, *, stage: str = "runtime") -> None:
        super().__init__(message)
        self.stage = stage  # "provider" (400) | "runtime" (502)


async def spawn_agent(
    *,
    provider: str,
    department_id: str,
    role: str,
    name: str,
    initial_prompt: str,
    sprite: str | None = None,
) -> tuple[AgentSession, str]:
    """Register + spawn a conversational agent and emit its SESSION_START so
    it renders in the office. Returns (AgentSession, first_response) — the
    session has status "active" and claude_session_id set. Raises SpawnError —
    the registry entry is left with status "error" and last_error set so it
    still shows up (greyed out) in the roster rather than vanishing."""
    conv = get_conversational_provider(provider)
    if conv is None:
        raise SpawnError(f"unknown provider: {provider}", stage="provider")

    registry = get_agent_registry()
    agent = registry.create(
        provider=provider,
        department_id=department_id,
        role=role,
        name=name,
        sprite=sprite,
    )
    if provider == "claude" and agent.workspace_dir:
        _write_memory_instructions(agent.workspace_dir)

    try:
        # bypassPermissions is safe here specifically because this agent runs
        # in its own isolated agent-workspaces/<id>/ directory, never the
        # user's real projects (see claude_cli_service.py's docstring).
        spawn_result = await conv.spawn(
            workspace_dir=agent.workspace_dir,
            initial_prompt=initial_prompt,
            mcp_config_path=agent.mcp_config_path,
            permission_mode="bypassPermissions",
            # Economical defaults (see AgentSession.model/effort) — the
            # initial spawn turn uses them too, not just later turns.
            model=agent.model,
            effort=agent.effort,
        )
    except ProviderError as exc:
        agent.status = "error"
        agent.last_error = str(exc)
        registry.save()
        raise SpawnError(f"failed to spawn agent: {exc}") from exc

    session_id = spawn_result.external_session_id
    if not session_id:
        agent.status = "error"
        agent.last_error = "provider did not return a resumable session id"
        registry.save()
        raise SpawnError(agent.last_error)

    agent.claude_session_id = session_id
    agent.status = "active"
    registry.save()

    # SESSION_START — creates the StateMachine, records working_dir (needed
    # for every future --resume call), department_id, and this agent's
    # role/name so its Lead renders as the spawned character directly.
    await _emit_session_start(agent)

    return agent, spawn_result.first_response
