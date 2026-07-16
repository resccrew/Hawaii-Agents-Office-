"""Autopilot — the autonomous studio brain that turns the task board into a
self-driving office.

The human's only job is to drop a task on the board. From there the CEO runs
the whole thing without further prompting:

  1. Human adds a task            -> CEO is told to OWN it: decompose it, hire
                                     or reuse the right specialists, assign the
                                     subtasks, brief everyone, and drive to done.
  2. A task is marked done         -> CEO is nudged to pick up the next
                                     unfinished task immediately (this is the
                                     "when one finishes, start the next" rule).
  3. CEO goes idle w/ open tasks   -> CEO is nudged to keep going — it must not
                                     stop while the board still has open work.

All three edges funnel through `_supervise`, which reads the board and enqueues
a directive to the CEO via the same best-effort ChatBridge queue a human chat
message uses (so it respects the interactive-turn safety gate and serialises
per session).

Anti-runaway: the idle edge fires a lot, so it is guarded. We never nag while
any worker is mid-turn (real work is happening; a completion will re-trigger
us), and if the set of open tasks stops changing across several idle nudges we
stop nudging until the board actually changes — otherwise the CEO could loop
"idle -> nudge -> idle" forever and burn tokens. Strong edges (new task / task
done) reset the stall counter because they represent genuine progress.
"""

from __future__ import annotations

import asyncio
import logging
import os

from app.core.agent_registry import AgentSession, get_agent_registry
from app.core.ceo import CEO_DEPARTMENT, CEO_ROLE
from app.core.chat_bridge import get_chat_bridge
from app.core.connection_manager import ConnectionManager
from app.core.event_processor import EventProcessor
from app.core.task_board import get_task_board
from app.models.tasks import SharedTask, TaskStatus

logger = logging.getLogger("studio_ops.autopilot")

# How many times we'll re-nudge an idle CEO about the SAME unchanged set of
# open tasks before giving up and waiting for the board to change (or the
# human to step in). Kept low on purpose: every nudge is a paid CEO turn, so
# we remind once and then wait rather than burning usage re-poking a stalled
# board.
MAX_STALL_NUDGES = 1


def _truncate(text: str | None, limit: int = 240) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _task_line(task: SharedTask) -> str:
    desc = _truncate(task.description, 160)
    suffix = f" — {desc}" if desc else ""
    return f"• {task.subject} (id: {task.id}, status: {task.status}){suffix}"


class Autopilot:
    def __init__(self, manager: ConnectionManager, processor: EventProcessor) -> None:
        self.manager = manager
        self.processor = processor
        # Default on; set STUDIO_OPS_AUTOPILOT=0 to run the studio manually.
        self.enabled = os.environ.get("STUDIO_OPS_AUTOPILOT", "1") != "0"
        self._lock = asyncio.Lock()
        self._last_open_sig: frozenset[str] | None = None
        self._stall = 0

    # -- registration ---------------------------------------------------
    def install(self) -> None:
        """Wire the autopilot into the task board (create/update edges) and
        the chat bridge (session-idle edge). Idempotent-ish: only call once
        at startup (see get_autopilot)."""
        get_task_board(self.manager).register_hook(self._on_task_event)
        get_chat_bridge(self.manager, self.processor).register_idle_hook(self._on_session_idle)

    # -- edges ----------------------------------------------------------
    async def _on_task_event(self, event: str, task: SharedTask) -> None:
        """Task-board hook. Fast: schedules the (potentially long) CEO turn
        as a background task so a create/update HTTP request returns at once."""
        if not self.enabled or task.department_id != CEO_DEPARTMENT:
            return
        if event == "created" and task.created_by_agent_id is None:
            # A human dropped a new task on the board — the primary trigger.
            asyncio.create_task(self._supervise("new_task", task))
        elif event == "updated" and task.status == TaskStatus.DONE:
            # Something got finished — advance to whatever's still open.
            asyncio.create_task(self._supervise("task_done", task))

    async def _on_session_idle(self, session_id: str) -> None:
        """ChatBridge idle hook — fires when a session's queue drains. We only
        care about the CEO going idle; schedule a supervisory check."""
        if not self.enabled:
            return
        ceo = self._ceo()
        if ceo is None or ceo.claude_session_id != session_id:
            return
        asyncio.create_task(self._supervise("idle"))

    async def kickstart(self) -> None:
        """Called once after the CEO is up at boot: if the board already has
        unfinished tasks (e.g. left over from a previous run, or added before
        the CEO finished starting), get the CEO moving on them right away."""
        if not self.enabled:
            return
        await self._supervise("resume")

    # -- core -----------------------------------------------------------
    def _ceo(self) -> AgentSession | None:
        for agent in get_agent_registry().list():
            if agent.role == CEO_ROLE and agent.status != "error":
                return agent
        return None

    def _any_worker_busy(self, ceo: AgentSession) -> bool:
        """True if any non-CEO agent is mid-turn. While a worker is actually
        working we stay quiet — its completion will re-trigger us."""
        bridge = get_chat_bridge(self.manager, self.processor)
        for agent in get_agent_registry().list():
            if agent.agent_id == ceo.agent_id or not agent.claude_session_id:
                continue
            if bridge.is_busy(agent.claude_session_id):
                return True
        return False

    async def _supervise(self, reason: str, task: SharedTask | None = None) -> None:
        if not self.enabled:
            return
        ceo = self._ceo()
        if ceo is None or not ceo.claude_session_id:
            # CEO not ready yet — a later board event or kickstart will retry.
            logger.debug("autopilot(%s): no ready CEO, skipping", reason)
            return

        bridge = get_chat_bridge(self.manager, self.processor)

        async with self._lock:
            prompt = self._decide(reason, ceo, task, bridge)
        if prompt is None:
            return

        sm = self.processor.get_or_create(ceo.claude_session_id)
        logger.info("autopilot(%s): driving CEO", reason)
        await bridge.enqueue_chat_message(sm, prompt)

    def _decide(
        self, reason: str, ceo: AgentSession, task: SharedTask | None, bridge
    ) -> str | None:
        """Pure-ish decision (under the lock): read the board, apply the
        anti-runaway rules, update dedup state, and return the directive text
        to send the CEO — or None to stay quiet."""
        board = get_task_board(self.manager)
        tasks = board.list_for_department(CEO_DEPARTMENT)
        pending = [t for t in tasks if t.status != TaskStatus.DONE]
        open_tasks = [t for t in tasks if t.status == TaskStatus.OPEN]

        if not pending:
            # Board is clear — reset and go quiet.
            self._last_open_sig = None
            self._stall = 0
            return None

        open_sig = frozenset(t.id for t in open_tasks)

        if reason == "idle":
            # Nothing unassigned to act on — remaining work is in_progress, so
            # someone's on it; wait for a completion instead of nagging.
            if not open_tasks:
                return None
            # A worker is actively churning — don't interrupt; its finish
            # re-triggers us.
            if self._any_worker_busy(ceo):
                return None
            # The CEO itself still has queued/among-flight work — let it run.
            if bridge.is_busy(ceo.claude_session_id):
                return None
            # Same open set as last time we nudged → the CEO isn't converting
            # open tasks into progress. Allow a few reminders, then stop.
            if open_sig == self._last_open_sig:
                self._stall += 1
                if self._stall > MAX_STALL_NUDGES:
                    logger.info("autopilot(idle): stalled on %d open task(s), pausing", len(open_tasks))
                    return None
            else:
                self._stall = 0
        else:
            # Strong edge (new_task / task_done / resume) = real change; reset.
            self._stall = 0

        self._last_open_sig = open_sig
        return self._build_prompt(reason, task, pending, open_tasks)

    def _build_prompt(
        self,
        reason: str,
        task: SharedTask | None,
        pending: list[SharedTask],
        open_tasks: list[SharedTask],
    ) -> str:
        board_lines = "\n".join(_task_line(t) for t in pending)
        playbook = (
            "Run this end-to-end, autonomously, without waiting for the human:\n"
            "1. Break each task into concrete subtasks with studio_create_task.\n"
            "2. Decide the roles you need, but keep the team SMALL to conserve "
            "usage — every agent and every turn costs limits. Strongly prefer "
            "reusing existing teammates (studio_list_agents), and hand one "
            "capable agent several related subtasks rather than hiring a new "
            "specialist per task. Only studio_spawn_agent when a needed skill is "
            "genuinely missing, and give every hire a specific briefing.\n"
            "3. Assign each subtask (studio_update_task with assignee_agent_id + "
            "status in_progress) and brief its owner with studio_send_message.\n"
            "4. Keep the board honest: mark tasks in_progress when work starts and "
            "done only when truly complete. When a task is marked done, its owner "
            "MUST pass studio_update_task a `result`: a short report plus a link or "
            "file path to the deliverable — that's what the human sees on the task. "
            "Instruct every agent you brief to do this.\n"
            "Do not stop while the board still has unfinished work. Reply concisely "
            "with what you did."
        )

        if reason == "new_task" and task is not None:
            head = (
                f"[AUTOPILOT] The human added a new task to the board:\n{_task_line(task)}\n\n"
                "Own it now."
            )
        elif reason == "task_done" and task is not None:
            head = (
                f"[AUTOPILOT] Task '{task.subject}' is done. "
                "Move straight on to the remaining unfinished work below — do not idle."
            )
        elif reason == "resume":
            head = (
                "[AUTOPILOT] The studio has unfinished tasks on the board. "
                "Resume and drive them to completion."
            )
        else:  # idle
            head = (
                "[AUTOPILOT] You have open, unstarted tasks and no one is working them. "
                "Pick them up now and push them forward."
            )

        return f"{head}\n\nCurrent unfinished board:\n{board_lines}\n\n{playbook}"


_autopilot: Autopilot | None = None


def get_autopilot(manager: ConnectionManager, processor: EventProcessor) -> Autopilot:
    global _autopilot
    if _autopilot is None:
        _autopilot = Autopilot(manager, processor)
        _autopilot.install()
    return _autopilot
