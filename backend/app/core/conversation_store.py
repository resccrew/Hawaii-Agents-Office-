"""Persists each session's chat conversation log to disk, mirroring
task_board.py's and agent_registry.py's JSON-snapshot pattern.

StateMachine.conversation was otherwise pure in-memory state: under
`uvicorn --reload` (routine in dev) or any crash/redeploy, EventProcessor's
entire `state_machines` dict is rebuilt from scratch, silently wiping every
agent's conversation history — an assistant reply the user had just read
would vanish the moment the process restarted, with nothing to indicate it
ever happened. This gives conversation the same restart-survival the task
board already has.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.sessions import ConversationEntry

STATE_FILE = Path.home() / "studio-ops" / "state" / "conversations.json"
# Cap growth per session — mirrors StateMachine.history's 200-entry cap.
# Chat turns are two entries each (prompt + response), so this is ~250 turns.
MAX_ENTRIES_PER_SESSION = 500


class ConversationStore:
    def __init__(self) -> None:
        self._data: dict[str, list[ConversationEntry]] = {}
        self._load()

    def get(self, session_id: str) -> list[ConversationEntry]:
        return list(self._data.get(session_id, []))

    def sync(self, session_id: str, conversation: list[ConversationEntry]) -> None:
        """Overwrite this session's persisted log with the StateMachine's
        current (already-authoritative) in-memory list — simpler and less
        error-prone than incremental appends, and cheap since this is only
        called twice per chat turn (see event_processor.py)."""
        entries = list(conversation)
        if len(entries) > MAX_ENTRIES_PER_SESSION:
            entries = entries[-MAX_ENTRIES_PER_SESSION:]
        self._data[session_id] = entries
        self._save()

    def _save(self) -> None:
        """Best-effort — never raises, so a disk hiccup can't break a chat
        turn that otherwise succeeded."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2))
            tmp.replace(STATE_FILE)
        except OSError:
            pass

    def _load(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            raw = json.loads(STATE_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            return
        # ConversationEntry is a TypedDict — plain dicts round-trip as-is.
        self._data = raw


_store: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store
