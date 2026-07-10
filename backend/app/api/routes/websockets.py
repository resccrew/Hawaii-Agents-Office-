"""Three observation WS endpoints, ported 1:1 in shape from claude-office's
api/routes/websockets.py. `receive_text()` is intentionally discarded in each
loop — these are keep-alive/disconnect-detection only, exactly like the
reference project. The chat channel (Phase 3) is deliberately NOT here; it
lives in routes/chat.py with real inbound message parsing, so this file's
discard-loop pattern is never at risk of silently swallowing a chat send."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.connection_manager import get_manager
from app.core.event_processor import get_processor

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def ws_session(websocket: WebSocket, session_id: str) -> None:
    manager = get_manager()
    await manager.connect_session(session_id, websocket)
    try:
        processor = get_processor(manager)
        sm = processor.get_or_create(session_id)
        snapshot = sm.snapshot()
        await websocket.send_json(
            {
                "type": "state_update",
                "timestamp": snapshot.last_updated.isoformat(),
                "session_id": session_id,
                "state": snapshot.model_dump(mode="json", by_alias=True),
            }
        )
        while True:
            await websocket.receive_text()  # keep-alive only, result discarded
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_session(session_id, websocket)


@router.websocket("/ws/overview")
async def ws_overview(websocket: WebSocket) -> None:
    manager = get_manager()
    await manager.connect_overview(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_overview(websocket)


@router.websocket("/ws/room/{room_id}")
async def ws_room(websocket: WebSocket, room_id: str) -> None:
    manager = get_manager()
    await manager.connect_room(room_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_room(room_id, websocket)
