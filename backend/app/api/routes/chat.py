"""Chat endpoints (Phase 3). REST send + dedicated /ws/chat/{session_id}
streaming channel, kept separate from the observation /ws/{session_id}
socket so chat backpressure/framing never competes with state_update
broadcast traffic (see compiled-dreaming-badger.md Phase 3 item 3)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.chat_bridge import get_chat_bridge
from app.core.connection_manager import get_manager
from app.core.event_processor import get_processor

rest_router = APIRouter()
ws_router = APIRouter()


class SendChatMessage(BaseModel):
    text: str


@rest_router.post("/chat/{session_id}/messages")
async def send_chat_message(session_id: str, payload: SendChatMessage) -> dict:
    manager = get_manager()
    processor = get_processor(manager)
    bridge = get_chat_bridge(manager, processor)
    sm = processor.get_or_create(session_id)

    # Fire-and-forget: the REST call returns immediately with "accepted" or
    # "queued"; the actual reply streams over /ws/chat/{session_id}. This
    # keeps the endpoint from blocking on however long the headless CLI call
    # takes (seconds to a couple minutes).
    was_active = sm.interactive_turn_active
    asyncio.create_task(bridge.enqueue_chat_message(sm, payload.text))
    return {"status": "queued" if was_active else "accepted"}


@ws_router.websocket("/ws/chat/{session_id}")
async def ws_chat(websocket: WebSocket, session_id: str) -> None:
    manager = get_manager()
    await manager.connect_chat(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive only; sends go via REST
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_chat(session_id, websocket)
