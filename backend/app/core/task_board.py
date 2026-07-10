"""In-memory shared task board — the structured half of Phase 6
coordination (complementary to direct agent-to-agent chat via
ChatBridge). Both the human (TaskBoard.tsx) and agents (via the
studio-ops MCP server's create_task/update_task tools) read/write through
this same store, scoped per department_id."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.connection_manager import ConnectionManager
from app.models.tasks import SharedTask, TaskStatus


class TaskBoard:
    def __init__(self, manager: ConnectionManager) -> None:
        self.manager = manager
        self._tasks: dict[str, SharedTask] = {}

    def list_for_department(self, department_id: str) -> list[SharedTask]:
        return sorted(
            (t for t in self._tasks.values() if t.department_id == department_id),
            key=lambda t: t.created_at,
        )

    async def create(
        self,
        *,
        department_id: str,
        subject: str,
        description: str | None,
        created_by_agent_id: str | None,
    ) -> SharedTask:
        task = SharedTask(
            id=f"task-{uuid.uuid4().hex[:10]}",
            department_id=department_id,
            subject=subject,
            description=description,
            created_by_agent_id=created_by_agent_id,
        )
        self._tasks[task.id] = task
        await self._broadcast(department_id)
        return task

    async def update(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        assignee_agent_id: str | None = None,
    ) -> SharedTask | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if status is not None:
            task.status = status
        if assignee_agent_id is not None:
            task.assignee_agent_id = assignee_agent_id
        task.updated_at = datetime.now(UTC)
        await self._broadcast(task.department_id)
        return task

    async def _broadcast(self, department_id: str) -> None:
        tasks = [t.model_dump(mode="json", by_alias=True) for t in self.list_for_department(department_id)]
        await self.manager.broadcast_task(
            department_id, {"type": "task_board_update", "departmentId": department_id, "tasks": tasks}
        )


_board: TaskBoard | None = None


def get_task_board(manager: ConnectionManager) -> TaskBoard:
    global _board
    if _board is None:
        _board = TaskBoard(manager)
    return _board
