"""Tests for the studio_memory_list/read/write MCP tools
(app/mcp/studio_ops_mcp.py). These are thin httpx wrappers over
/api/v1/memory, already covered at the HTTP layer by test_memory_routes.py
— this file exercises the actual tool functions an agent calls, including
the scope-defaults-to-caller's-own-agent-id behavior.

No real network/subprocess: httpx.AsyncClient is monkeypatched to route
through an ASGITransport straight into the FastAPI app in-process, the same
approach FastAPI's own TestClient uses under the hood — the MCP server
normally talks to a real running uvicorn, but nothing about that is
load-bearing for what these tools do with the response."""

from __future__ import annotations

import httpx
import pytest

from app.core import memory_store as ms
from app.main import app
from app.mcp import studio_ops_mcp as tools

_RealAsyncClient = httpx.AsyncClient


class _ASGIAsyncClient(_RealAsyncClient):
    def __init__(self, *args, **kwargs) -> None:
        kwargs["transport"] = httpx.ASGITransport(app=app)
        kwargs["base_url"] = "http://testserver"
        super().__init__(*args, **kwargs)


@pytest.fixture(autouse=True)
def _isolated_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "AGENT_WORKSPACES_ROOT", tmp_path / "agent-workspaces")
    monkeypatch.setattr(ms, "OFFICE_MEMORY_ROOT", tmp_path / "state" / "office-memory")
    monkeypatch.setattr(httpx, "AsyncClient", _ASGIAsyncClient)
    yield


async def test_write_then_list_then_read_office_scope() -> None:
    written = await tools.studio_memory_write(
        "convention", "Convention", "how we name things", "kebab-case everywhere.", scope="office"
    )
    assert written["slug"] == "convention"
    assert written["type"] == "project"

    index = await tools.studio_memory_list(scope="office")
    assert [e["slug"] for e in index] == ["convention"]

    fact = await tools.studio_memory_read("convention", scope="office")
    assert fact["body"] == "kebab-case everywhere."


async def test_scope_defaults_to_callers_own_agent_id(monkeypatch) -> None:
    monkeypatch.setattr(tools, "CALLER_AGENT_ID", "agent-test000000")

    await tools.studio_memory_write("progress", "Progress", "d", "did X, next is Y")
    index = await tools.studio_memory_list()
    assert [e["slug"] for e in index] == ["progress"]

    # Confirm it actually landed under the agent's own scope, not office.
    office_index = await tools.studio_memory_list(scope="office")
    assert office_index == []

    fact = await tools.studio_memory_read("progress")
    assert fact["scope"] == "agent-test000000"


async def test_write_rejects_invalid_type() -> None:
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await tools.studio_memory_write("bad", "Bad", "d", "body", type="not-a-type", scope="office")
    assert exc_info.value.response.status_code == 400
