"""spawn_agent() must refuse to spawn once the studio is at MAX_AGENTS,
so an over-eager CEO/autopilot loop can't hire an unbounded team. The
check+insert is atomic (see agent_registry.create_if_room) so this holds
even under concurrent spawns."""

from __future__ import annotations

import pytest

from app.core import agent_registry as ar
from app.core import agent_spawner as spawner
from app.services.providers.base import ConversationalProvider, SpawnResult


class _FakeProvider(ConversationalProvider):
    name = "fake"

    async def spawn(self, **kwargs) -> SpawnResult:
        return SpawnResult(external_session_id=f"fake-session-{id(kwargs)}", first_response="hi")

    def send(self, **kwargs):  # pragma: no cover - unused by this test
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, "AGENT_WORKSPACES_ROOT", tmp_path / "agent-workspaces")
    monkeypatch.setattr(ar, "STATE_FILE", tmp_path / "state" / "agents.json")
    ar._registry = None
    yield
    ar._registry = None


@pytest.fixture(autouse=True)
def _fake_provider(monkeypatch):
    monkeypatch.setattr(spawner, "get_conversational_provider", lambda name: _FakeProvider())


@pytest.fixture(autouse=True)
def _no_op_session_start(monkeypatch):
    async def _noop(agent) -> None:
        return None

    monkeypatch.setattr(spawner, "_emit_session_start", _noop)


async def test_spawn_agent_raises_once_at_max_agents(monkeypatch) -> None:
    monkeypatch.setattr(spawner, "MAX_AGENTS", 2)

    for i in range(2):
        await spawner.spawn_agent(
            provider="claude",
            department_id="engineering",
            role="programmer",
            name=f"agent-{i}",
            initial_prompt="build X",
        )

    with pytest.raises(spawner.SpawnError) as exc_info:
        await spawner.spawn_agent(
            provider="claude",
            department_id="engineering",
            role="programmer",
            name="one-too-many",
            initial_prompt="build X",
        )
    assert exc_info.value.stage == "provider"
    assert "limit" in str(exc_info.value)

    registry = ar.get_agent_registry()
    assert len(registry.list()) == 2
