"""AgentRegistry hygiene: removing an agent must clean up what would
otherwise be orphaned on disk (its workspace and chat-uploads directory),
and spawning must never be able to overshoot MAX_AGENTS even under
concurrent calls (create_if_room's check + insert happen under one lock)."""

from __future__ import annotations

import asyncio

import pytest

from app.core import agent_registry as ar
from app.core import attachments


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, "AGENT_WORKSPACES_ROOT", tmp_path / "agent-workspaces")
    monkeypatch.setattr(ar, "STATE_FILE", tmp_path / "state" / "agents.json")
    monkeypatch.setattr(attachments, "ATTACH_ROOT", tmp_path / "chat-uploads")
    ar._registry = None
    yield
    ar._registry = None


def test_remove_deletes_workspace_dir() -> None:
    registry = ar.get_agent_registry()
    agent = registry.create(provider="claude", department_id="engineering", role="programmer", name="Ada")
    workspace = agent.workspace_dir
    assert workspace is not None
    from pathlib import Path

    assert Path(workspace).exists()

    assert registry.remove(agent.agent_id) is True
    assert not Path(workspace).exists()
    assert registry.get(agent.agent_id) is None


def test_remove_deletes_orphaned_uploads_dir() -> None:
    registry = ar.get_agent_registry()
    agent = registry.create(provider="claude", department_id="engineering", role="programmer", name="Ada")
    agent.claude_session_id = "session-123"

    uploads_dir = attachments.ATTACH_ROOT / "session-123"
    uploads_dir.mkdir(parents=True)
    (uploads_dir / "file.txt").write_text("hi")

    registry.remove(agent.agent_id)

    assert not uploads_dir.exists()


def test_remove_missing_agent_is_a_no_op() -> None:
    registry = ar.get_agent_registry()
    assert registry.remove("agent-does-not-exist") is False


def test_remove_survives_workspace_already_gone() -> None:
    """A workspace deleted out-of-band (e.g. by the user) must not make
    remove() raise — cleanup is best-effort."""
    registry = ar.get_agent_registry()
    agent = registry.create(provider="claude", department_id="engineering", role="programmer", name="Ada")
    import shutil

    shutil.rmtree(agent.workspace_dir)

    assert registry.remove(agent.agent_id) is True


async def test_create_if_room_respects_max_agents() -> None:
    registry = ar.get_agent_registry()
    for i in range(3):
        created = await registry.create_if_room(
            max_agents=3, provider="claude", department_id="engineering", role="programmer", name=f"a{i}"
        )
        assert created is not None

    over_limit = await registry.create_if_room(
        max_agents=3, provider="claude", department_id="engineering", role="programmer", name="one-too-many"
    )
    assert over_limit is None
    assert len(registry.list()) == 3


async def test_create_if_room_atomic_under_concurrency() -> None:
    """Two concurrent create_if_room calls racing the same cap must not
    both succeed and overshoot it — the check-then-insert happens under
    one asyncio.Lock, so this must never create more than max_agents."""
    registry = ar.get_agent_registry()

    async def spawn_one(name: str):
        return await registry.create_if_room(
            max_agents=1, provider="claude", department_id="engineering", role="programmer", name=name
        )

    results = await asyncio.gather(spawn_one("a"), spawn_one("b"))
    succeeded = [r for r in results if r is not None]
    assert len(succeeded) == 1
    assert len(registry.list()) == 1
