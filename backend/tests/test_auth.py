"""Verifies the auth layer conftest.py overrides to a no-op for every other
test in this suite. Each test here explicitly restores the real dependency
for its own duration (try/finally) rather than relying on fixture-ordering
around the session-wide override, so it stays correct regardless of test
execution order."""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core import auth, git_ops
from app.core.workspace_registry import WorkspaceRegistry
from app.main import app

client = TestClient(app)


@contextmanager
def _real_auth_enforced():
    """Temporarily remove conftest.py's blanket override so these tests
    exercise the actual require_api_key / enforce_ws_auth dependencies."""
    saved: dict = {}
    for dep in (auth.require_api_key, auth.enforce_ws_auth):
        if dep in app.dependency_overrides:
            saved[dep] = app.dependency_overrides.pop(dep)
    try:
        yield
    finally:
        app.dependency_overrides.update(saved)


def test_rest_rejects_missing_token() -> None:
    with _real_auth_enforced():
        resp = client.get("/api/v1/agents")
        assert resp.status_code == 401


def test_rest_rejects_wrong_token() -> None:
    with _real_auth_enforced():
        resp = client.get("/api/v1/agents", headers={"X-API-Key": "not-the-real-token"})
        assert resp.status_code == 401


def test_rest_accepts_valid_token() -> None:
    with _real_auth_enforced():
        resp = client.get("/api/v1/agents", headers={"X-API-Key": auth.get_token()})
        assert resp.status_code == 200


def test_health_stays_open_without_token() -> None:
    # /health is deliberately NOT behind api_key_dep in main.py (liveness
    # probe hooks/tooling can poll before a token even exists) — assert
    # that stays true even with real enforcement on for every other route.
    with _real_auth_enforced():
        resp = client.get("/health")
        assert resp.status_code == 200


def test_ws_rejects_missing_token() -> None:
    with _real_auth_enforced():
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/overview"):
                pass
        assert exc_info.value.code == 1008


def test_ws_rejects_disallowed_origin_even_with_valid_token() -> None:
    with _real_auth_enforced():
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/ws/overview?token={auth.get_token()}",
                headers={"Origin": "http://evil.example.com"},
            ):
                pass
        assert exc_info.value.code == 1008


def test_ws_accepts_valid_token_no_origin() -> None:
    with _real_auth_enforced():
        with client.websocket_connect(f"/ws/overview?token={auth.get_token()}"):
            pass  # accepted — no exception


def test_ws_accepts_valid_token_with_allowed_origin() -> None:
    with _real_auth_enforced():
        with client.websocket_connect(
            f"/ws/overview?token={auth.get_token()}",
            headers={"Origin": "http://localhost:3010"},
        ):
            pass


def test_git_add_repo_rejects_path_outside_home() -> None:
    with pytest.raises(ValueError, match="outside the allowed roots"):
        git_ops.add_repo("/private/tmp/studio-ops-auth-test-outside-home")


def test_git_add_repo_rejects_token_directory() -> None:
    with pytest.raises(ValueError, match="outside the allowed roots"):
        git_ops.add_repo(str(auth.TOKEN_DIR))


def test_workspace_create_rejects_path_outside_home(tmp_path, monkeypatch) -> None:
    # Point the registry's own snapshot file at a scratch location so this
    # test can't collide with (or corrupt) a real ~/studio-ops/state/workspaces.json.
    monkeypatch.setattr("app.core.workspace_registry.STATE_FILE", tmp_path / "workspaces.json")
    registry = WorkspaceRegistry()
    # _seed_from_git_ops() may have already populated one entry from the
    # real (unrelated) git_ops state on construction — capture that
    # baseline rather than assuming an empty registry.
    before = registry.list()
    with tempfile.TemporaryDirectory(dir="/private/tmp" if Path("/private/tmp").exists() else None) as outside:
        with pytest.raises(ValueError, match="outside the allowed roots"):
            registry.create(name="evil", repo_path=outside, department_id="Engineering")
        # The rejected path must not have been registered in memory either —
        # this is the ordering bug fixed alongside the allowlist check.
        assert registry.list() == before


def test_terminal_create_rejects_cwd_outside_home() -> None:
    with _real_auth_enforced():
        resp = client.post(
            "/api/v1/terminal",
            headers={"X-API-Key": auth.get_token()},
            json={"workspace_id": "w1", "cwd": "/private/tmp", "kind": "shell"},
        )
        assert resp.status_code == 400
