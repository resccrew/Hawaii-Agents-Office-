"""Phase 1 verification: fixture events POSTed through /api/v1/events must
drive the StateMachine transitions and end up in the broadcast snapshot,
with no live Claude Code session or hook involved."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.connection_manager import get_manager
from app.core.event_processor import get_processor
from app.main import app

client = TestClient(app)


def _event(event_type: str, session_id: str, **data) -> dict:
    return {
        "event_type": event_type,
        "session_id": session_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": data,
    }


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_session_lifecycle_drives_lead_state() -> None:
    session_id = "fixture-session-001"

    resp = client.post("/api/v1/events", json=_event("session_start", session_id))
    assert resp.status_code == 200, resp.text

    sm = get_processor(get_manager()).get_or_create(session_id)
    assert sm.lead.state == "idle"
    assert sm.interactive_turn_active is False

    resp = client.post(
        "/api/v1/events",
        json=_event("user_prompt_submit", session_id, prompt="write a jump-and-run controller"),
    )
    assert resp.status_code == 200, resp.text
    assert sm.interactive_turn_active is True
    assert sm.lead.state == "receiving"
    assert sm.conversation[-1]["text"] == "write a jump-and-run controller"
    assert sm.conversation[-1]["source"] == "interactive"

    resp = client.post(
        "/api/v1/events",
        json=_event("pre_tool_use", session_id, tool_name="Edit"),
    )
    assert resp.status_code == 200, resp.text
    assert sm.lead.state == "working"
    assert sm.interactive_turn_active is True

    resp = client.post("/api/v1/events", json=_event("stop", session_id))
    assert resp.status_code == 200, resp.text
    assert sm.lead.state == "idle"
    assert sm.interactive_turn_active is False, "chat bridge gate must clear on Stop"
    assert sm.lead.chat_available is True


def test_subagent_lifecycle_creates_and_removes_dev() -> None:
    session_id = "fixture-session-002"

    client.post("/api/v1/events", json=_event("session_start", session_id))
    client.post(
        "/api/v1/events",
        json=_event(
            "subagent_start",
            session_id,
            agent_id="dev-1",
            agent_name="Programmer Bot",
            task_description="implement jump physics",
        ),
    )

    sm = get_processor(get_manager()).get_or_create(session_id)
    assert "dev-1" in sm.devs
    assert sm.devs["dev-1"].state == "arriving"
    assert sm.lead.state == "delegating"

    client.post(
        "/api/v1/events",
        json=_event("subagent_stop", session_id, agent_id="dev-1", result_summary="done"),
    )
    assert sm.devs["dev-1"].state == "leaving"

    client.post("/api/v1/events", json=_event("cleanup", session_id, agent_id="dev-1"))
    assert "dev-1" not in sm.devs


def test_chat_event_tagged_distinct_from_interactive() -> None:
    session_id = "fixture-session-003"
    client.post("/api/v1/events", json=_event("session_start", session_id))
    client.post(
        "/api/v1/events",
        json=_event("chat_message", session_id, prompt="status?", response_text="all good"),
    )

    sm = get_processor(get_manager()).get_or_create(session_id)
    sources = [c["source"] for c in sm.conversation if c.get("source")]
    assert "chat" in sources
    assert sm.interactive_turn_active is False, "chat events must not flip the interactive gate"


def test_rejects_malformed_event() -> None:
    resp = client.post(
        "/api/v1/events",
        json={"event_type": "not_a_real_type", "session_id": "x", "data": {}},
    )
    assert resp.status_code == 422


def test_websocket_delivers_initial_snapshot() -> None:
    session_id = "fixture-session-004"
    client.post("/api/v1/events", json=_event("session_start", session_id))

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "state_update"
        assert msg["session_id"] == session_id
        assert msg["state"]["lead"]["state"] == "idle"


def test_timeline_unknown_session_is_404() -> None:
    resp = client.get("/api/v1/sessions/never-seen-session/timeline")
    assert resp.status_code == 404


def test_timeline_returns_events_oldest_first() -> None:
    session_id = "fixture-session-timeline-order"
    client.post("/api/v1/events", json=_event("session_start", session_id))
    client.post(
        "/api/v1/events",
        json=_event("user_prompt_submit", session_id, prompt="first"),
    )
    client.post("/api/v1/events", json=_event("stop", session_id))

    resp = client.get(f"/api/v1/sessions/{session_id}/timeline")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session_id"] == session_id
    types = [e["type"] for e in body["events"]]
    assert types == ["session_start", "user_prompt_submit", "stop"]


def test_timeline_ring_buffer_caps_at_limit() -> None:
    from app.core.state_machine import TIMELINE_HISTORY_LIMIT

    session_id = "fixture-session-timeline-cap"
    overflow = 5
    for _ in range(TIMELINE_HISTORY_LIMIT + overflow):
        resp = client.post("/api/v1/events", json=_event("waiting", session_id))
        assert resp.status_code == 200

    resp = client.get(f"/api/v1/sessions/{session_id}/timeline")
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    assert len(events) == TIMELINE_HISTORY_LIMIT, "oldest entries must be dropped, not the newest"


def test_timeline_rejects_missing_token() -> None:
    from app.core import auth
    from app.main import app

    session_id = "fixture-session-timeline-auth"
    client.post("/api/v1/events", json=_event("session_start", session_id))

    saved = {}
    for dep in (auth.require_api_key, auth.enforce_ws_auth):
        if dep in app.dependency_overrides:
            saved[dep] = app.dependency_overrides.pop(dep)
    try:
        resp = client.get(f"/api/v1/sessions/{session_id}/timeline")
        assert resp.status_code == 401
        resp = client.get(
            f"/api/v1/sessions/{session_id}/timeline",
            headers={"X-API-Key": auth.get_token()},
        )
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.update(saved)
