"""Three observation WS endpoints, ported 1:1 in shape from claude-office's
api/routes/websockets.py. `receive_text()` is intentionally discarded in each
loop — these are keep-alive/disconnect-detection only, exactly like the
reference project. The chat channel (Phase 3) is deliberately NOT here; it
lives in routes/chat.py with real inbound message parsing, so this file's
discard-loop pattern is never at risk of silently swallowing a chat send.

CRITICAL ordering note: `/ws/overview` MUST be registered before
`/ws/{session_id}`. Starlette matches WS routes in registration order, and
"overview" is a syntactically valid value for the `{session_id}` path
parameter — with the catch-all registered first, every connection to
`/ws/overview` was silently swallowed by `ws_session`, creating a bogus
StateMachine literally keyed "overview" instead of ever reaching
`ws_overview` below. Found by testing: /ws/overview's initial-snapshot
broadcast always contained exactly one empty, roleless entry — that phantom
session, not a real agent. `/ws/room/{room_id}` doesn't have this problem
(three path segments vs. two, so it can't collide with `/ws/{session_id}`),
but is kept above the catch-all too for the same reason to be safe.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.connection_manager import get_manager
from app.core.event_processor import get_processor, is_registered_agent

router = APIRouter()


@router.websocket("/ws/overview")
async def ws_overview(websocket: WebSocket) -> None:
    manager = get_manager()
    await manager.connect_overview(websocket)
    try:
        # Initial-snapshot-on-connect (same treatment as /ws/room/{room_id}
        # below): without this, connecting after agents are already
        # standing around renders nothing until each of them happens to
        # produce its next event.
        processor = get_processor(manager)
        for sm in processor.state_machines.values():
            # Registry-backed agents only — see is_registered_agent. Keeps
            # phantom hook-observed sessions out of the studio office.
            if not is_registered_agent(sm.session_id):
                continue
            snapshot = sm.snapshot()
            await websocket.send_json(
                {
                    "type": "state_update",
                    "timestamp": snapshot.last_updated.isoformat(),
                    "session_id": sm.session_id,
                    "state": snapshot.model_dump(mode="json", by_alias=True),
                }
            )
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
        # Same initial-snapshot fix as /ws/overview above — a room
        # connecting to a department with agents already standing there
        # otherwise rendered completely empty until each of those
        # sessions' *next* event happened to fire.
        processor = get_processor(manager)
        for sm in processor.state_machines.values():
            if sm.department_id != room_id:
                continue
            snapshot = sm.snapshot()
            await websocket.send_json(
                {
                    "type": "state_update",
                    "timestamp": snapshot.last_updated.isoformat(),
                    "session_id": sm.session_id,
                    "state": snapshot.model_dump(mode="json", by_alias=True),
                }
            )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_room(room_id, websocket)


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
