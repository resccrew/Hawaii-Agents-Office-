"""REST tests for /api/v1/memory — the memory_store unit tests already
cover path safety/atomicity/limits in isolation; this covers the HTTP
plumbing (status codes, request/response shapes) on top of it.

Isolated from the real ~/studio-ops state via the same
AGENT_WORKSPACES_ROOT/OFFICE_MEMORY_ROOT monkeypatch memory_store's own
tests use — importing app.main pulls in the full app, but nothing here
touches disk outside tmp_path."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import memory_store as ms
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "AGENT_WORKSPACES_ROOT", tmp_path / "agent-workspaces")
    monkeypatch.setattr(ms, "OFFICE_MEMORY_ROOT", tmp_path / "state" / "office-memory")
    yield


def test_write_then_list_then_read() -> None:
    resp = client.put(
        "/api/v1/memory/office/style",
        json={"name": "Style", "description": "how we work", "type": "project", "body": "Body."},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["slug"] == "style"
    assert data["body"] == "Body."

    resp = client.get("/api/v1/memory/office")
    assert resp.status_code == 200
    assert [e["slug"] for e in resp.json()] == ["style"]

    resp = client.get("/api/v1/memory/office/style")
    assert resp.status_code == 200
    assert resp.json()["description"] == "how we work"


def test_read_missing_fact_is_404() -> None:
    resp = client.get("/api/v1/memory/office/does-not-exist")
    assert resp.status_code == 404


def test_write_invalid_type_is_400() -> None:
    resp = client.put(
        "/api/v1/memory/office/bad",
        json={"name": "x", "description": "x", "type": "not-a-type", "body": "x"},
    )
    assert resp.status_code == 400


def test_traversal_scope_is_rejected_not_500() -> None:
    # A literal ".." gets normalized away by URL resolution before it ever
    # reaches the app (`/memory/..` -> `/`, a 404 from routing, never our
    # handler) — good, but means the percent-encoded form is the one that
    # actually exercises memory_store's own InvalidScope check end to end.
    resp = client.get("/api/v1/memory/%2E%2E")
    assert resp.status_code == 400


def test_delete_round_trip() -> None:
    client.put(
        "/api/v1/memory/office/temp",
        json={"name": "Temp", "description": "d", "type": "project", "body": "x"},
    )
    resp = client.delete("/api/v1/memory/office/temp")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    resp = client.get("/api/v1/memory/office/temp")
    assert resp.status_code == 404


def test_agent_and_office_scopes_are_independent_over_http() -> None:
    client.put(
        "/api/v1/memory/agent-xyz/note",
        json={"name": "N", "description": "d", "type": "project", "body": "agent"},
    )
    client.put(
        "/api/v1/memory/office/note",
        json={"name": "N", "description": "d", "type": "project", "body": "office"},
    )
    assert client.get("/api/v1/memory/agent-xyz/note").json()["body"] == "agent"
    assert client.get("/api/v1/memory/office/note").json()["body"] == "office"
