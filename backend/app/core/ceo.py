"""The studio CEO — a single always-on coordinator agent, auto-started when
the backend boots. Unlike worker agents (spawned on demand by the human via
"+ agent"), the CEO exists from launch so the human has someone to hand a
high-level goal to. The CEO then breaks that goal into tasks, spawns the
right specialist agents (studio_spawn_agent MCP tool), assigns work
(studio_create_task / studio_update_task), and keeps everyone coordinated
(studio_send_message).

Idempotency: the CEO is a normal AgentSession with role "ceo", so it
persists in agents.json like any other. `ensure_ceo()` is a no-op if a
non-errored CEO already exists — critical under `uvicorn --reload`, which
re-runs startup on every code change and must NOT spawn a fresh CEO each
time.
"""

from __future__ import annotations

import logging

from app.core.agent_registry import get_agent_registry
from app.core.agent_spawner import SpawnError, spawn_agent

logger = logging.getLogger("studio_ops.ceo")

CEO_ROLE = "ceo"
CEO_NAME = "CEO"
# The CEO and (by its own default) the work it delegates live in this
# department, so everything is visible in the default UI task tab without a
# department switcher.
CEO_DEPARTMENT = "Engineering"

CEO_PROMPT = """You are the CEO of "Pixel Forge", an indie game-dev studio. You coordinate a \
team of AI agents; you do NOT do the hands-on work yourself.

You have these Studio Ops tools (all prefixed studio_ — they are the studio's \
own tools, distinct from any built-in tools):
- studio_spawn_agent(department_id, role, name, initial_prompt): hire a new \
teammate. role is one of: programmer, game_designer, artist, qa_tester, \
producer. The initial_prompt is that agent's first briefing — be specific \
about what they should build.
- studio_list_agents(): see who is currently on the team and their session ids.
- studio_send_message(target_session_id, message): message a teammate directly \
to coordinate, unblock, or follow up.
- studio_create_task(department_id, subject, description): put a task on the \
shared board everyone can see.
- studio_list_tasks(department_id): read the current board.
- studio_update_task(task_id, status, assignee_agent_id): move a task \
(open/in_progress/done) or assign it.

Default department for tasks and hires is "Engineering" unless the human says \
otherwise.

How you work when the human gives you a goal:
1. Restate the goal briefly and outline a short plan.
2. Break it into concrete tasks with studio_create_task.
3. Decide which roles you need. For each, studio_spawn_agent with a clear \
briefing, then studio_update_task to assign the relevant task to that agent.
4. Use studio_send_message to hand each agent their first instruction and to \
follow up.
5. Keep the board current as work progresses.

Do NOT hire anyone or create tasks yet — right now just briefly introduce \
yourself as the studio CEO and say you're ready for the human's first goal. \
Keep it to two short sentences."""


def _find_ceo():
    for agent in get_agent_registry().list():
        if agent.role == CEO_ROLE:
            return agent
    return None


async def ensure_ceo() -> None:
    """Spawn the CEO once, if not already present. Safe to call on every
    startup. Never raises — a failed CEO spawn must not take down the
    server (the human can still spawn workers manually)."""
    existing = _find_ceo()
    if existing is not None and existing.status != "error":
        logger.info("CEO already present (%s, status=%s) — skipping spawn", existing.agent_id, existing.status)
        return

    if existing is not None:
        # Previous CEO errored out — drop it and try a clean spawn.
        get_agent_registry().remove(existing.agent_id)

    logger.info("Auto-starting studio CEO…")
    try:
        agent, _ = await spawn_agent(
            provider="claude",
            department_id=CEO_DEPARTMENT,
            role=CEO_ROLE,
            name=CEO_NAME,
            initial_prompt=CEO_PROMPT,
        )
        logger.info("CEO ready: %s (session %s)", agent.agent_id, agent.claude_session_id)
    except SpawnError as exc:
        logger.warning("CEO auto-start failed (will retry on next boot): %s", exc)
