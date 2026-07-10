"""Shared task board endpoints (Phase 6). REST CRUD + a dedicated
/ws/tasks/{department_id} broadcast channel, mirroring the chat.py split
into rest_router/ws_router so main.py mounts them under different prefixes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.connection_manager import get_manager
from app.core.task_board import get_task_board
from app.models.tasks import SharedTask, TaskStatus

rest_router = APIRouter()
ws_router = APIRouter()


class CreateTaskRequest(BaseModel):
    department_id: str
    subject: str
    description: str | None = None
    created_by_agent_id: str | None = None


class UpdateTaskRequest(BaseModel):
    status: TaskStatus | None = None
    assignee_agent_id: str | None = None


@rest_router.get("/tasks", response_model=list[SharedTask])
async def list_tasks(department_id: str) -> list[SharedTask]:
    board = get_task_board(get_manager())
    return board.list_for_department(department_id)


@rest_router.post("/tasks", response_model=SharedTask)
async def create_task(payload: CreateTaskRequest) -> SharedTask:
    board = get_task_board(get_manager())
    return await board.create(
        department_id=payload.department_id,
        subject=payload.subject,
        description=payload.description,
        created_by_agent_id=payload.created_by_agent_id,
    )


@rest_router.patch("/tasks/{task_id}", response_model=SharedTask)
async def update_task(task_id: str, payload: UpdateTaskRequest) -> SharedTask:
    board = get_task_board(get_manager())
    task = await board.update(
        task_id, status=payload.status, assignee_agent_id=payload.assignee_agent_id
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@ws_router.websocket("/ws/tasks/{department_id}")
async def ws_tasks(websocket: WebSocket, department_id: str) -> None:
    manager = get_manager()
    await manager.connect_task(department_id, websocket)
    try:
        board = get_task_board(manager)
        tasks = [t.model_dump(mode="json", by_alias=True) for t in board.list_for_department(department_id)]
        await websocket.send_json(
            {"type": "task_board_update", "departmentId": department_id, "tasks": tasks}
        )
        while True:
            await websocket.receive_text()  # keep-alive only
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_task(department_id, websocket)
