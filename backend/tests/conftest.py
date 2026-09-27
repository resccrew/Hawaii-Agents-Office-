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

import pytest

from app.core import (
    agent_registry,
    attachments,
    chat_bridge,
    conversation_store,
    git_ops,
    memory_store,
    settings_store,
    task_board,
    workspace_registry,
)


@pytest.fixture(autouse=True)
def isolate_real_user_state(tmp_path, monkeypatch):
    """Every module below computes its on-disk state path once, at import
    time, from Path.home() — e.g. git_ops.STATE_FILE is
    ~/studio-ops/state/git.json on whatever machine runs the suite. Left
    unpatched, tests read and write *this developer's* real state: on the
    machine this was found on, that file's "active" repo pointed at an
    iCloud-synced clone, and git against an iCloud path hangs — so
    test_workspace_create_rejects_path_outside_home (which builds a real
    WorkspaceRegistry, which seeds itself from git_ops.list_state()) hung
    the whole suite. Nothing here should ever touch a real path belonging
    to whoever's laptop happens to run pytest, so every module-level path
    constant is redirected under this test's own tmp_path, and HOME itself
    is patched for the few call sites (git_ops.is_allowed_repo_path,
    terminal.py's cwd check) that call Path.home() live instead of caching
    it. The lazy singleton caches (_store/_registry/...) are also reset so
    a fresh instance is built against *this* test's paths instead of
    reusing one a previous test already constructed against its own
    (by-then-deleted) tmp_path."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(git_ops, "STATE_FILE", home / "studio-ops" / "state" / "git.json")
    monkeypatch.setattr(git_ops, "REPOS_DIR", home / "studio-ops" / "repos")
    monkeypatch.setattr(git_ops, "_DENIED_ROOTS", (home / ".studio-ops", home / ".ssh"))

    monkeypatch.setattr(agent_registry, "STATE_FILE", home / "studio-ops" / "state" / "agents.json")
    monkeypatch.setattr(agent_registry, "AGENT_WORKSPACES_ROOT", home / "studio-ops" / "agent-workspaces")

    # memory_store's agent scope IS agent_registry's own workspace dir
    # (facts live directly in agent-workspaces/{id}/, not a subfolder) —
    # same root, kept in sync with the line above rather than duplicated.
    monkeypatch.setattr(memory_store, "AGENT_WORKSPACES_ROOT", agent_registry.AGENT_WORKSPACES_ROOT)
    monkeypatch.setattr(memory_store, "OFFICE_MEMORY_ROOT", home / "studio-ops" / "state" / "office-memory")

    monkeypatch.setattr(attachments, "ATTACH_ROOT", home / "studio-ops" / "chat-uploads")

    monkeypatch.setattr(auth, "TOKEN_DIR", home / ".studio-ops")
    monkeypatch.setattr(auth, "TOKEN_FILE", home / ".studio-ops" / "api-token")
    monkeypatch.setattr(auth, "_token_cache", None)

    monkeypatch.setattr(chat_bridge, "LOCK_DIR", home / ".claude" / "studio-ops-locks")

    monkeypatch.setattr(conversation_store, "STATE_FILE", home / "studio-ops" / "state" / "conversations.json")
    monkeypatch.setattr(settings_store, "STATE_FILE", home / "studio-ops" / "state" / "settings.json")
    monkeypatch.setattr(task_board, "STATE_FILE", home / "studio-ops" / "state" / "tasks.json")
    monkeypatch.setattr(workspace_registry, "STATE_FILE", home / "studio-ops" / "state" / "workspaces.json")

    monkeypatch.setattr(settings_store, "_store", None)
    monkeypatch.setattr(agent_registry, "_registry", None)
    monkeypatch.setattr(conversation_store, "_store", None)
    monkeypatch.setattr(task_board, "_board", None)
    monkeypatch.setattr(workspace_registry, "_registry", None)

    yield home
