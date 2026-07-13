"""Phase 3 mandatory test (compiled-dreaming-badger.md, Phase 3 step 6):
a chat message sent while the session has an active interactive turn must
queue, not fire immediately, and must auto-drain once the turn ends —
exercised here against a real throwaway `claude -p` session (created once,
out-of-band) rather than a mock, since the whole point of this phase is
validating the actual CLI mechanism.

IMPORTANT — why this hits a live server over real HTTP/WS instead of using
Starlette's TestClient: TestClient runs the ASGI app inside its own
thread-backed event-loop portal. `asyncio.create_subprocess_exec` (used by
claude_cli_service.py) does not reliably get scheduled to actually run
inside that portal thread — observed as `enqueue_chat_message`'s
fire-and-forget `asyncio.create_task` never completing, hanging the test on
`ws.receive_json()` forever, even though the exact same call sequence
against a real running `uvicorn` process completes in ~3s. Real subprocess
spawning needs a real event loop; a live server (started separately, e.g.
via `uvicorn app.main:app --port 8010`) sidesteps this entirely. Skips
cleanly if no server is reachable there.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime

import httpx
import pytest
import websockets

BASE_URL = "http://localhost:8010"
WS_BASE = "ws://localhost:8010"

FIXTURE_SESSION_ID = "cd7eacb2-1546-48dd-b834-b1a60c036172"
FIXTURE_CWD = (
    "/private/tmp/claude-501/-Users-pravorovnikita/"
    "c77f6e53-0417-417c-92db-7160b02894d4/scratchpad/chat-bridge-test"
)


def _server_reachable() -> bool:
    try:
        httpx.get(f"{BASE_URL}/health", timeout=1.0)
        return True
    except httpx.HTTPError:
        return False


requires_live_server_and_cli = pytest.mark.skipif(
    shutil.which("claude") is None or not _server_reachable(),
    reason="requires both the claude CLI and a live studio-ops server on :8010 "
    "(start with: cd backend && .venv/bin/uvicorn app.main:app --port 8010)",
)


def _event(event_type: str, session_id: str, **data) -> dict:
    return {
        "event_type": event_type,
        "session_id": session_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": data,
    }


async def _recv(ws, timeout: float = 10) -> dict:
    """recv() that transparently discards a leading `chat_history` frame.
    The fixture session below is reused (and its conversation now persists
    to disk — see conversation_store.py), so a fresh connection may replay
    its accumulated history as the very first frame before anything this
    test triggers. That's correct production behavior, not something these
    behavioral tests care about — they assert on the specific event
    sequence a given action produces, which chat_history isn't part of."""
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        if msg.get("type") == "chat_history":
            continue
        return msg


async def _recv_until_terminal(ws, max_messages: int = 10) -> list[dict]:
    received = []
    for _ in range(max_messages):
        msg = await _recv(ws, timeout=30)
        received.append(msg)
        if msg.get("type") in ("chat_turn_complete", "chat_error"):
            break
    return received


@requires_live_server_and_cli
async def test_chat_queues_while_busy_and_drains_on_stop() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL) as http:
        async with websockets.connect(f"{WS_BASE}/ws/chat/{FIXTURE_SESSION_ID}") as ws:
            # Simulate an in-flight interactive terminal turn. working_dir
            # must match where the fixture session was created — --resume
            # fails outside that directory.
            await http.post(
                "/api/v1/events",
                json=_event(
                    "pre_tool_use", FIXTURE_SESSION_ID, tool_name="Edit", working_dir=FIXTURE_CWD
                ),
            )

            resp = await http.post(
                f"/api/v1/chat/{FIXTURE_SESSION_ID}/messages",
                json={"text": "One more time, in <=6 words: what word did I first ask for?"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "queued"

            queued_msg = await _recv(ws)
            assert queued_msg["type"] == "chat_queued"

            # Terminal goes idle — must auto-drain via the EventProcessor
            # post-hook, with no further action from us.
            await http.post("/api/v1/events", json=_event("stop", FIXTURE_SESSION_ID))

            started = await _recv(ws)
            assert started["type"] == "chat_turn_started"

            trail = await _recv_until_terminal(ws)
            assert trail, "never received a terminal chat event"
            final = trail[-1]
            assert final["type"] == "chat_turn_complete", final
            assert "pong" in final["text"].lower(), final["text"]


@requires_live_server_and_cli
async def test_chat_sends_immediately_when_session_idle() -> None:
    # Deliberately its own test, not chained immediately after the one
    # above within the same run: back-to-back `claude -p --resume` calls
    # against the same session_id were observed to hang the *second* call
    # indefinitely (not an artifact of our asyncio.Lock serialization —
    # that already guarantees no *concurrent* calls; this looks like the
    # CLI itself needing a moment to settle the session file between
    # invocations). Run this test file with -k to target one test at a
    # time if both need to pass in the same sitting.
    async with httpx.AsyncClient(base_url=BASE_URL) as http:
        async with websockets.connect(f"{WS_BASE}/ws/chat/{FIXTURE_SESSION_ID}") as ws:
            resp = await http.post(
                f"/api/v1/chat/{FIXTURE_SESSION_ID}/messages", json={"text": "Say OK"}
            )
            assert resp.json()["status"] == "accepted"

            trail = await _recv_until_terminal(ws)
            assert trail, "never received a terminal chat event"
            assert trail[0]["type"] == "chat_turn_started"
            assert trail[-1]["type"] == "chat_turn_complete", trail[-1]
