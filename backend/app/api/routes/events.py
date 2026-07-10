"""POST /events — hook ingestion endpoint, ported from claude-office's
api/routes/events.py. Validates the incoming flat JSON payload against the
AnyEvent discriminated union and hands it to the EventProcessor."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.core.connection_manager import get_manager
from app.core.event_processor import get_processor
from app.models.events import EventAdapter

router = APIRouter()


@router.post("/events")
async def ingest_event(payload: dict) -> dict:
    try:
        event = EventAdapter.validate_python(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    processor = get_processor(get_manager())
    sm = await processor.process(event)
    return {"status": "ok", "session_id": sm.session_id}
