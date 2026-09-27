"""Unit coverage for TaskBoard.delete itself: fires the "deleted" hook,
persists the removal, and returns None for an already-gone task — the
REST layer (test_task_delete.py) covers the HTTP plumbing on top of
this."""

from __future__ import annotations

from app.core import task_board as tb
from app.core.connection_manager import ConnectionManager


async def test_delete_fires_deleted_hook(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tb, "STATE_FILE", tmp_path / "tasks.json")
    board = tb.TaskBoard(ConnectionManager())

    events: list[tuple[str, str]] = []

    async def hook(event: str, task) -> None:
        events.append((event, task.id))

    board.register_hook(hook)

    task = await board.create(
        department_id="engineering", subject="do X", description=None, created_by_agent_id=None
    )
    removed = await board.delete(task.id)

    assert removed is not None
    assert removed.id == task.id
    assert ("deleted", task.id) in events
    assert board.get(task.id) is None


async def test_delete_missing_task_returns_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tb, "STATE_FILE", tmp_path / "tasks.json")
    board = tb.TaskBoard(ConnectionManager())
    assert await board.delete("task-missing") is None


async def test_delete_persists_removal(tmp_path, monkeypatch) -> None:
    state_file = tmp_path / "tasks.json"
    monkeypatch.setattr(tb, "STATE_FILE", state_file)
    board = tb.TaskBoard(ConnectionManager())
    task = await board.create(
        department_id="engineering", subject="do X", description=None, created_by_agent_id=None
    )
    await board.delete(task.id)

    reloaded = tb.TaskBoard(ConnectionManager())
    assert reloaded.get(task.id) is None
