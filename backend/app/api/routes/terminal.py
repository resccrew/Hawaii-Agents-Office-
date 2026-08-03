"""Terminal pane endpoints — the PTY-backed, bidirectional counterpart to
chat.py's headless/JSON channels. See services/terminal_service.py's module
docstring for why this needed a real long-lived process instead of the
per-turn subprocess model every other provider uses, and
connection_manager.py for why it needed a new binary WS channel."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.connection_manager import get_manager
from app.core.terminal_registry import get_terminal_registry
from app.models.terminal import TerminalKind, TerminalPane

rest_router = APIRouter()
ws_router = APIRouter()


class CreatePaneRequest(BaseModel):
    workspace_id: str
    cwd: str
    kind: TerminalKind = "shell"


class ResizeRequest(BaseModel):
    rows: int
    cols: int


@rest_router.post("/terminal", response_model=TerminalPane)
async def create_pane(payload: CreatePaneRequest) -> TerminalPane:
    registry = get_terminal_registry()
    try:
        return await registry.create(workspace_id=payload.workspace_id, kind=payload.kind, cwd=payload.cwd)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@rest_router.get("/terminal", response_model=list[TerminalPane])
async def list_panes(workspace_id: str | None = None) -> list[TerminalPane]:
    return get_terminal_registry().list(workspace_id=workspace_id)


@rest_router.delete("/terminal/{pane_id}")
async def delete_pane(pane_id: str) -> dict:
    if not get_terminal_registry().remove(pane_id):
        raise HTTPException(status_code=404, detail="pane not found")
    return {"paneId": pane_id, "status": "closed"}


@rest_router.post("/terminal/{pane_id}/resize")
async def resize_pane(pane_id: str, payload: ResizeRequest) -> dict:
    if not get_terminal_registry().resize(pane_id, payload.rows, payload.cols):
        raise HTTPException(status_code=404, detail="pane not found")
    return {"ok": True}


@ws_router.websocket("/ws/terminal/{pane_id}")
async def ws_terminal(websocket: WebSocket, pane_id: str) -> None:
    registry = get_terminal_registry()
    if registry.get_live(pane_id) is None:
        # Reject before accept()ing — same "unknown id, don't pretend to
        # connect" contract a 404 gives on the REST side, just spelled in
        # WS close-code terms since there's no HTTP status here.
        await websocket.close(code=4404)
        return

    manager = get_manager()
    await manager.connect_terminal(pane_id, websocket)
    try:
        # Unlike every other WS endpoint in this codebase (server-push-only,
        # client sends are keep-alive noise), this one is genuinely
        # bidirectional: every binary frame from the client is a keystroke
        # written straight to the PTY's master fd.
        while True:
            data = await websocket.receive_bytes()
            registry.write(pane_id, data)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_terminal(pane_id, websocket)
