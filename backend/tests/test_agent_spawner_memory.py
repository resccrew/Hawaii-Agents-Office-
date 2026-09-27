"""spawn_agent() must drop a CLAUDE.md with the memory-discipline
instructions into a claude-provider agent's workspace before its first
turn (so the instruction is in the agent's own cwd — the thing Claude Code
itself reads automatically — not just a one-off spawn prompt it can
scroll out of context). Non-claude providers get no such file: they have
no equivalent cwd-convention and the memory MCP tools are Claude-only
today (see studio_ops_mcp.py's docstring on the studio_* tool prefix)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import agent_registry as ar
from app.core import agent_spawner as spawner
from app.services.providers.base import ConversationalProvider, SpawnResult


class _FakeProvider(ConversationalProvider):
    name = "fake"

    async def spawn(self, **kwargs) -> SpawnResult:
        return SpawnResult(external_session_id="fake-session-1", first_response="hi")

    def send(self, **kwargs):  # pragma: no cover - unused by this test
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, "AGENT_WORKSPACES_ROOT", tmp_path / "agent-workspaces")
    monkeypatch.setattr(ar, "STATE_FILE", tmp_path / "state" / "agents.json")
    ar._registry = None  # drop the module-level singleton so it re-reads the patched paths
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


async def test_claude_agent_gets_memory_instructions_in_workspace() -> None:
    agent, _ = await spawner.spawn_agent(
        provider="claude", department_id="engineering", role="programmer", name="Ada", initial_prompt="build X"
    )
    claude_md = Path(agent.workspace_dir, "CLAUDE.md")
    assert claude_md.is_file()
    content = claude_md.read_text()
    assert "studio_memory_list" in content
    assert "studio_memory_write" in content


async def test_non_claude_agent_gets_no_claude_md() -> None:
    agent, _ = await spawner.spawn_agent(
        provider="openai", department_id="engineering", role="programmer", name="GPT", initial_prompt="build X"
    )
    assert not Path(agent.workspace_dir, "CLAUDE.md").exists()


def test_memory_instructions_preserves_existing_user_content(tmp_path) -> None:
    """A workspace whose CLAUDE.md already has real user content (e.g.
    seeded from a real project checkout) must keep that content verbatim
    — only the memory block is added/updated, never a full overwrite."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    claude_md = workspace / "CLAUDE.md"
    user_text = "# My Project\n\nSome important rules the human wrote.\n"
    claude_md.write_text(user_text, encoding="utf-8")

    spawner._write_memory_instructions(str(workspace))

    content = claude_md.read_text(encoding="utf-8")
    assert user_text.strip() in content
    assert spawner.MEMORY_BLOCK_BEGIN in content
    assert "studio_memory_write" in content


def test_memory_instructions_idempotent_on_repeat_calls(tmp_path) -> None:
    """Calling _write_memory_instructions twice (e.g. respawn) must not
    duplicate the block or the user's own content — the second call
    replaces only what's between the markers."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    claude_md = workspace / "CLAUDE.md"
    claude_md.write_text("# My Project\n\nRule one.\n", encoding="utf-8")

    spawner._write_memory_instructions(str(workspace))
    spawner._write_memory_instructions(str(workspace))

    content = claude_md.read_text(encoding="utf-8")
    assert content.count(spawner.MEMORY_BLOCK_BEGIN) == 1
    assert content.count(spawner.MEMORY_BLOCK_END) == 1
    assert content.count("Rule one.") == 1
    assert content.count(spawner.MEMORY_INSTRUCTIONS) == 1


def test_memory_instructions_creates_file_when_missing(tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    spawner._write_memory_instructions(str(workspace))
    content = (workspace / "CLAUDE.md").read_text(encoding="utf-8")
    assert spawner.MEMORY_BLOCK_BEGIN in content
    assert spawner.MEMORY_BLOCK_END in content
