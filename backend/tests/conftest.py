"""Session-wide default: the API-key/WS-auth dependencies (app/core/auth.py)
are overridden to no-ops here so the pre-existing behavioral tests
(test_event_pipeline.py, test_chat_bridge.py) keep exercising the state
machine without threading a token through every call — exactly what
FastAPI's `dependency_overrides` exists for. test_auth.py pops these
overrides per-test to verify the real enforcement instead."""

from __future__ import annotations

from app.core import auth
from app.main import app

app.dependency_overrides[auth.require_api_key] = lambda: None
app.dependency_overrides[auth.enforce_ws_auth] = lambda: None
