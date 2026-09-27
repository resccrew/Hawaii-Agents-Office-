"""ChatBridge.__init__ must clean up stale *.lock files left in LOCK_DIR by
a hard-killed process (SIGKILL skips the `finally` that would normally
remove one) — otherwise orphans accumulate forever across restarts. A
lock file has no runtime effect within a single process (defense-in-depth
only, per the module docstring), so clearing all of them on startup is
safe."""

from __future__ import annotations

from app.core import chat_bridge as cb
from app.core.connection_manager import ConnectionManager
from app.core.event_processor import EventProcessor


def test_stale_lock_files_removed_on_construction(tmp_path, monkeypatch) -> None:
    lock_dir = tmp_path / "locks"
    monkeypatch.setattr(cb, "LOCK_DIR", lock_dir)
    lock_dir.mkdir(parents=True)
    stale = lock_dir / "orphaned-session.lock"
    stale.write_text("")
    (lock_dir / "not-a-lock.txt").write_text("keep me")

    manager = ConnectionManager()
    cb.ChatBridge(manager, EventProcessor(manager))

    assert not stale.exists()
    assert (lock_dir / "not-a-lock.txt").exists()


def test_construction_survives_empty_lock_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cb, "LOCK_DIR", tmp_path / "fresh-locks")
    manager = ConnectionManager()
    cb.ChatBridge(manager, EventProcessor(manager))  # must not raise
