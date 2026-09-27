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

# Belt-and-suspenders sweep on top of the event-driven edges above: every 15
# minutes, check whether there's unfinished work (including tasks marked
# in_progress) that nobody appears to be actively driving — the gap none of
# the event-driven edges can see is a task an agent was assigned to but
# silently stopped working on without ever hitting the Stop/idle hook (a
# dropped hook, a crashed subprocess). If the board is clear or genuinely
# moving, this is a no-op — no CEO turn, no cost.
PERIODIC_INTERVAL_SECONDS = 15 * 60
# Same anti-runaway idea as MAX_STALL_NUDGES, tracked separately (this sweep
# uses a different definition of "actionable" — it also counts in_progress
# tasks, which "idle" deliberately does not) so the two dedup counters don't
# clobber each other.
MAX_PERIODIC_STALL_NUDGES = 1


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
        # Dedup state for the periodic sweep — deliberately separate from
        # the "idle" edge's own _last_open_sig/_stall (see
        # MAX_PERIODIC_STALL_NUDGES above).
        self._periodic_task: asyncio.Task | None = None
        self._last_periodic_sig: frozenset[str] | None = None
        self._periodic_stall = 0

    # -- registration ---------------------------------------------------
    def install(self) -> None:
        """Wire the autopilot into the task board (create/update edges) and
        the chat bridge (session-idle edge). Idempotent-ish: only call once
        at startup (see get_autopilot)."""
        get_task_board(self.manager).register_hook(self._on_task_event)
        get_chat_bridge(self.manager, self.processor).register_idle_hook(self._on_session_idle)

    def start_periodic_check(self) -> None:
        """Start the 15-minute sweep. Safe to call more than once — a second
        call is a no-op while the loop from the first is still running (e.g.
        under `uvicorn --reload` re-entering create_app)."""
        if not self.enabled or self._periodic_task is not None:
            return
        self._periodic_task = asyncio.create_task(self._periodic_loop())

    def stop_periodic_check(self) -> None:
        if self._periodic_task is not None:
            self._periodic_task.cancel()
            self._periodic_task = None

    async def _periodic_loop(self) -> None:
        while True:
            await asyncio.sleep(PERIODIC_INTERVAL_SECONDS)
            try:
                await self._supervise("periodic")
            except Exception:
                # A failed sweep must not kill the loop — the next
                # iteration retries in another 15 minutes rather than
                # silently disabling the sweep until a restart.
                logger.exception("autopilot: periodic sweep failed")

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
        elif reason == "periodic":
            # A worker is actively churning — don't interrupt; its eventual
            # completion re-triggers the "idle" edge above.
            if self._any_worker_busy(ceo):
                return None
            # The CEO itself is already mid-turn (queued/in-flight) — let it
            # run rather than piling on a second nudge.
            if bridge.is_busy(ceo.claude_session_id):
                return None
            # Unlike "idle", this also counts in_progress tasks — that's the
            # whole point of the sweep: catch a task an agent was assigned
            # but silently stopped working on (no worker busy, no Stop/idle
            # hook ever fired to re-trigger the event-driven edges above).
            stalled_sig = frozenset(t.id for t in pending)
            if stalled_sig == self._last_periodic_sig:
                self._periodic_stall += 1
                if self._periodic_stall > MAX_PERIODIC_STALL_NUDGES:
                    logger.info(
                        "autopilot(periodic): stalled on %d task(s) across sweeps, staying quiet",
                        len(pending),
                    )
                    return None
            else:
                self._periodic_stall = 0
            self._last_periodic_sig = stalled_sig
            return self._build_prompt(reason, task, pending, open_tasks)
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
        display_pending = pending[:25]
        board_lines = "\n".join(_task_line(t) for t in display_pending)
        if len(pending) > 25:
            board_lines += f"\n... and {len(pending) - 25} more unfinished tasks."
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
        elif reason == "periodic":
            head = (
                "[AUTOPILOT] Periodic 15-minute check-in: the board still has "
                "unfinished work (including tasks marked in_progress) and no one "
                "appears to be actively working right now. Check studio_list_agents "
                "and studio_list_tasks — if an assignee has gone quiet on an "
                "in_progress task, follow up with studio_send_message or reassign it. "
                "If there's genuinely nothing actionable, say so briefly; otherwise "
                "push the stalled work forward."
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
