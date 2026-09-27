"""Shared task board endpoints (Phase 6). REST CRUD + a dedicated
/ws/tasks/{department_id} broadcast channel, mirroring the chat.py split
into rest_router/ws_router so main.py mounts them under different prefixes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core import auth
from app.core.agent_spawner import SpawnError, spawn_agent
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
    result: str | None = None


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
        task_id,
        status=payload.status,
        assignee_agent_id=payload.assignee_agent_id,
        result=payload.result,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


class DispatchTaskRequest(BaseModel):
    # DevRole value (see models/agents.py) — which kind of agent to spawn
    # against this task. "programmer" covers the common kanban case; the
    # caller can override for e.g. a QA/design task.
    role: str = "programmer"


class DispatchTaskResponse(BaseModel):
    task: SharedTask
    agent_id: str
    session_id: str


@rest_router.post("/tasks/{task_id}/dispatch", response_model=DispatchTaskResponse)
async def dispatch_task(task_id: str, payload: DispatchTaskRequest | None = None) -> DispatchTaskResponse:
    """Kanban drag-to-dispatch: spawns a coding agent against a task and
    moves it to in_progress. Deliberately its own endpoint rather than a
    side effect of PATCH /tasks/{id} — a human manually self-claiming a
    task (a plain status change) must not accidentally spawn an agent.

    Composes three already-existing services rather than inventing new
    orchestration: agent_spawner.spawn_agent (registry + provider spawn +
    SESSION_START, the exact same pipeline POST /api/v1/agents uses) and
    TaskBoard.update (which already broadcasts over the /ws/tasks channel
    the kanban UI listens on).
    """
    board = get_task_board(get_manager())
    task = board.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if task.assignee_agent_id:
        raise HTTPException(status_code=409, detail="task already dispatched")

    role = (payload.role if payload else None) or "programmer"
    prompt = task.subject if not task.description else f"{task.subject}\n\n{task.description}"

    try:
        agent, _first_response = await spawn_agent(
            provider="claude",
            department_id=task.department_id,
            role=role,
            name=task.subject[:40],
            initial_prompt=(
                "You've been assigned this task from the shared kanban board:\n\n"
                f"{prompt}\n\n"
                "Work on it, then reply with a short summary of what you did — "
                "the human reviews and marks it done from the board."
            ),
        )
    except SpawnError as exc:
        status_code = 400 if exc.stage == "provider" else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    updated = await board.update(task_id, status=TaskStatus.IN_PROGRESS, assignee_agent_id=agent.agent_id)
    assert updated is not None  # task existed a moment ago and dispatch doesn't delete it
    assert agent.claude_session_id is not None  # spawn_agent always sets this on success
    return DispatchTaskResponse(task=updated, agent_id=agent.agent_id, session_id=agent.claude_session_id)


@ws_router.websocket("/ws/tasks/{department_id}")
async def ws_tasks(
    websocket: WebSocket, department_id: str, _auth: None = Depends(auth.enforce_ws_auth)
) -> None:
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
