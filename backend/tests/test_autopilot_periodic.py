"""The 15-minute periodic sweep (reason="periodic") — a belt-and-suspenders
edge on top of the event-driven ones, catching a task an agent was
assigned to but silently stopped working on (no Stop/idle hook ever
fired). Exercises Autopilot._decide directly (a pure-ish, synchronous
decision function) against real TaskBoard/AgentRegistry instances rooted
under tmp_path, with a fake ChatBridge standing in for `bridge.is_busy`.
"""

from __future__ import annotations

import pytest

from app.core import agent_registry as ar
from app.core import autopilot as ap
from app.core import ceo
from app.core import task_board as tb
from app.core.connection_manager import ConnectionManager
from app.core.event_processor import EventProcessor
from app.models.tasks import TaskStatus


class _FakeBridge:
    def __init__(self, busy: bool = False) -> None:
        self._busy = busy

    def is_busy(self, session_id: str) -> bool:
        return self._busy


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, "AGENT_WORKSPACES_ROOT", tmp_path / "agent-workspaces")
    monkeypatch.setattr(ar, "STATE_FILE", tmp_path / "state" / "agents.json")
    monkeypatch.setattr(tb, "STATE_FILE", tmp_path / "state" / "tasks.json")
    ar._registry = None
    yield
    ar._registry = None


def _make_autopilot() -> tuple[ap.Autopilot, tb.TaskBoard]:
    manager = ConnectionManager()
    processor = EventProcessor(manager)
    board = tb.TaskBoard(manager)
    autopilot = ap.Autopilot(manager, processor)
    # Autopilot looks up the board via get_task_board(self.manager), which
    # is a module-level singleton keyed only by having been constructed
    # once — reset it so it points at THIS test's board.
    tb._board = board
    return autopilot, board


def _make_ceo() -> ar.AgentSession:
    registry = ar.get_agent_registry()
    agent = registry.create(
        provider="claude", department_id=ceo.CEO_DEPARTMENT, role=ceo.CEO_ROLE, name="CEO"
    )
    agent.claude_session_id = "ceo-session"
    return agent


async def test_periodic_returns_prompt_when_task_stalled_and_nobody_busy() -> None:
    autopilot, board = _make_autopilot()
    ceo_agent = _make_ceo()
    task = await board.create(
        department_id=ceo.CEO_DEPARTMENT, subject="stuck task", description=None, created_by_agent_id=None
    )
    await board.update(task.id, status=TaskStatus.IN_PROGRESS)

    prompt = autopilot._decide("periodic", ceo_agent, None, _FakeBridge(busy=False))

    assert prompt is not None
    assert "Periodic 15-minute check-in" in prompt


async def test_periodic_stays_quiet_when_a_worker_is_busy(monkeypatch) -> None:
    autopilot, board = _make_autopilot()
    ceo_agent = _make_ceo()
    task = await board.create(
        department_id=ceo.CEO_DEPARTMENT, subject="stuck task", description=None, created_by_agent_id=None
    )
    await board.update(task.id, status=TaskStatus.IN_PROGRESS)

    monkeypatch.setattr(autopilot, "_any_worker_busy", lambda ceo: True)

    prompt = autopilot._decide("periodic", ceo_agent, None, _FakeBridge(busy=False))
    assert prompt is None


async def test_periodic_stays_quiet_when_ceo_itself_busy() -> None:
    autopilot, board = _make_autopilot()
    ceo_agent = _make_ceo()
    task = await board.create(
        department_id=ceo.CEO_DEPARTMENT, subject="stuck task", description=None, created_by_agent_id=None
    )
    await board.update(task.id, status=TaskStatus.IN_PROGRESS)

    prompt = autopilot._decide("periodic", ceo_agent, None, _FakeBridge(busy=True))
    assert prompt is None


async def test_periodic_anti_runaway_stops_nudging_same_stalled_set() -> None:
    """Regression guard: the same unchanged stalled task set must not keep
    generating nudges forever — after MAX_PERIODIC_STALL_NUDGES repeats
    with no board change, the sweep goes quiet."""
    autopilot, board = _make_autopilot()
    ceo_agent = _make_ceo()
    task = await board.create(
        department_id=ceo.CEO_DEPARTMENT, subject="stuck task", description=None, created_by_agent_id=None
    )
    await board.update(task.id, status=TaskStatus.IN_PROGRESS)

    bridge = _FakeBridge(busy=False)
    first = autopilot._decide("periodic", ceo_agent, None, bridge)
    assert first is not None

    # Nudge budget is MAX_PERIODIC_STALL_NUDGES=1: one more repeat is still
    # allowed, then it must go quiet.
    second = autopilot._decide("periodic", ceo_agent, None, bridge)
    assert second is not None

    third = autopilot._decide("periodic", ceo_agent, None, bridge)
    assert third is None


async def test_periodic_resets_stall_when_board_changes() -> None:
    autopilot, board = _make_autopilot()
    ceo_agent = _make_ceo()
    task = await board.create(
        department_id=ceo.CEO_DEPARTMENT, subject="stuck task", description=None, created_by_agent_id=None
    )
    await board.update(task.id, status=TaskStatus.IN_PROGRESS)

    bridge = _FakeBridge(busy=False)
    autopilot._decide("periodic", ceo_agent, None, bridge)
    autopilot._decide("periodic", ceo_agent, None, bridge)

    # A new task changes the pending signature — the stall counter for the
    # NEW signature starts fresh, so a nudge is allowed again immediately.
    await board.create(
        department_id=ceo.CEO_DEPARTMENT, subject="another task", description=None, created_by_agent_id=None
    )
    fresh = autopilot._decide("periodic", ceo_agent, None, bridge)
    assert fresh is not None


async def test_start_periodic_check_schedules_a_task_and_stop_cancels_it() -> None:
    manager = ConnectionManager()
    processor = EventProcessor(manager)
    autopilot = ap.Autopilot(manager, processor)

    autopilot.start_periodic_check()
    assert autopilot._periodic_task is not None
    task = autopilot._periodic_task

    # Calling start again while one is running must be a no-op (same task).
    autopilot.start_periodic_check()
    assert autopilot._periodic_task is task

    autopilot.stop_periodic_check()
    assert autopilot._periodic_task is None
    import asyncio as _asyncio

    with pytest.raises(_asyncio.CancelledError):
        await task
    assert task.cancelled()


def test_start_periodic_check_no_op_when_autopilot_disabled(monkeypatch) -> None:
    manager = ConnectionManager()
    processor = EventProcessor(manager)
    autopilot = ap.Autopilot(manager, processor)
    autopilot.enabled = False

    autopilot.start_periodic_check()
    assert autopilot._periodic_task is None
