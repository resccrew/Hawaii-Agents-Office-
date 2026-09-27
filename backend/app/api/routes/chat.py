"""Chat endpoints (Phase 3). REST send + dedicated /ws/chat/{session_id}
streaming channel, kept separate from the observation /ws/{session_id}
socket so chat backpressure/framing never competes with state_update
broadcast traffic (see compiled-dreaming-badger.md Phase 3 item 3)."""

from __future__ import annotations

import asyncio
import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core import auth
from app.core.attachments import AttachmentIn, SavedAttachment, save_attachment
from app.core.chat_bridge import get_chat_bridge
from app.core.connection_manager import get_manager
from app.core.event_processor import get_processor

rest_router = APIRouter()
ws_router = APIRouter()

# Generous enough for photos/screenshots and small documents, small enough
# that a chat POST can't be used to smuggle in something absurd — this is a
# local dev tool, not a hardened upload service, but a basic cap costs
# nothing and prevents an accidental multi-hundred-MB request from wedging
# a turn.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 25 * 1024 * 1024


class ChatAttachmentIn(BaseModel):
    filename: str
    mime_type: str = "application/octet-stream"
    data_base64: str


class SendChatMessage(BaseModel):
    text: str
    # Claude-only (`claude -p --model --effort`), chosen per-message from
    # ChatWindow.tsx's selector — ignored server-side for any other
    # provider (see chat_bridge.py / the provider's own send()).
    model: str | None = None
    effort: str | None = None
    attachments: list[ChatAttachmentIn] = []


def _decode_attachments(session_id: str, raw: list[ChatAttachmentIn]) -> list[SavedAttachment]:
    total = 0
    saved: list[SavedAttachment] = []
    for a in raw:
        try:
            data = base64.b64decode(a.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid base64 for attachment: {a.filename}") from exc
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=413, detail=f"attachment too large: {a.filename} (max {MAX_ATTACHMENT_BYTES} bytes)"
            )
        total += len(data)
        if total > MAX_TOTAL_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail="attachments too large in total for one message")
        saved.append(save_attachment(session_id, AttachmentIn(filename=a.filename, mime_type=a.mime_type, data=data)))
    return saved


@rest_router.post("/chat/{session_id}/messages")
async def send_chat_message(session_id: str, payload: SendChatMessage) -> dict:
    manager = get_manager()
    processor = get_processor(manager)
    bridge = get_chat_bridge(manager, processor)
    sm = processor.get_or_create(session_id)

    attachments = _decode_attachments(session_id, payload.attachments)

    # Fire-and-forget: the REST call returns immediately with "accepted" or
    # "queued"; the actual reply streams over /ws/chat/{session_id}. This
    # keeps the endpoint from blocking on however long the headless CLI call
    # takes (seconds to a couple minutes).
    was_active = sm.interactive_turn_active
    asyncio.create_task(
        bridge.enqueue_chat_message(
            sm, payload.text, model=payload.model, effort=payload.effort, attachments=attachments
        )
    )
    return {"status": "queued" if was_active else "accepted"}


@ws_router.websocket("/ws/chat/{session_id}")
async def ws_chat(websocket: WebSocket, session_id: str, _auth: None = Depends(auth.enforce_ws_auth)) -> None:
    manager = get_manager()
    await manager.connect_chat(session_id, websocket)
    try:
        # Replay persisted history on connect — same initial-snapshot
        # treatment /ws/overview and /ws/room/{id} already give the
        # observation channels. Without this, a chat window that opens (or
        # reconnects, e.g. after a network blip or backend restart) after
        # messages were already exchanged shows nothing until the *next*
        # live event — every reply already given looks silently lost. Only
        # "chat"-sourced entries: this channel only ever renders chat-bridge
        # turns, never a hook-observed interactive session's own turns.
        processor = get_processor(manager)
        sm = processor.get_or_create(session_id)
        history = [e for e in sm.conversation if e.get("source") == "chat"]
        if history:
            await websocket.send_json({
                "type": "chat_history",
                "messages": [
                    {"id": e["id"], "role": e["role"], "text": e["text"]} for e in history
                ],
            })
        while True:
            await websocket.receive_text()  # keep-alive only; sends go via REST
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_chat(session_id, websocket)
