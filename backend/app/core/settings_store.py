"""Runtime-configurable provider settings — API keys, local endpoints —
editable from the UI (Settings panel) instead of only via environment
variables set before the server starts. Persists to disk (mirrors
task_board.py's JSON-snapshot pattern) so a value entered once survives
restarts.

Resolution order: a value saved through the UI always wins over the
STUDIO_OPS_* env var of the same name — the UI is the more recent,
explicit action, and this is what lets someone paste a key into Settings
and have it take effect immediately without restarting the backend or
touching their shell environment. The env var stays as a fallback for
anyone who prefers configuring via deployment/CI instead of the UI.

Secrets are never echoed back over the API in full — GET /settings returns
a masked preview (last 4 characters) so the UI can confirm "yes, a key is
set, and it looks like the one I pasted" without re-exposing it on every
page load.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

STATE_FILE = Path.home() / "studio-ops" / "state" / "settings.json"

# (key, label, kind, default_hint) — the single source of truth for both
# what the settings API returns and what env var each key falls back to.
# kind "secret" gets masked in snapshot_masked(); "text" is shown as-is
# (base URLs/model names aren't sensitive).
SETTING_FIELDS: list[tuple[str, str, str]] = [
    ("openai_api_key", "OpenAI API key", "secret"),
    ("openai_model", "OpenAI model", "text"),
    ("gemini_api_key", "Gemini API key", "secret"),
    ("gemini_model", "Gemini model", "text"),
    ("ollama_base_url", "Ollama base URL", "text"),
    ("ollama_model", "Ollama model", "text"),
    ("nanobanana_api_key", "Nano Banana (image gen) API key", "secret"),
]

ENV_VAR_BY_KEY: dict[str, str] = {
    "openai_api_key": "STUDIO_OPS_OPENAI_API_KEY",
    "openai_model": "STUDIO_OPS_OPENAI_MODEL",
    "gemini_api_key": "STUDIO_OPS_GEMINI_API_KEY",
    "gemini_model": "STUDIO_OPS_GEMINI_MODEL",
    "ollama_base_url": "STUDIO_OPS_OLLAMA_BASE_URL",
    "ollama_model": "STUDIO_OPS_OLLAMA_MODEL",
    "nanobanana_api_key": "STUDIO_OPS_NANOBANANA_API_KEY",
}

_KNOWN_KEYS = {key for key, _, _ in SETTING_FIELDS}


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


class SettingsStore:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._load()

    def get(self, key: str) -> str | None:
        """Resolved value: saved override wins if set & non-empty, else
        the STUDIO_OPS_* env var of the same name, else None."""
        value = self._data.get(key)
        if value:
            return value
        env_name = ENV_VAR_BY_KEY.get(key)
        return (os.environ.get(env_name) or None) if env_name else None

    def set_many(self, values: dict[str, str]) -> None:
        """Applies a batch of edits from the settings form. An empty
        string clears a saved override (falls back to the env var again,
        if any) rather than saving an empty value — how a user "unsets"
        a field from the UI."""
        changed = False
        for key, raw in values.items():
            if key not in _KNOWN_KEYS:
                continue
            value = raw.strip()
            if value:
                self._data[key] = value
            else:
                self._data.pop(key, None)
            changed = True
        if changed:
            self._save()

    def snapshot_masked(self) -> list[dict]:
        rows = []
        for key, label, kind in SETTING_FIELDS:
            override = self._data.get(key)
            resolved = self.get(key)
            source = "override" if override else ("env" if resolved else "unset")
            preview = None
            if resolved:
                preview = _mask(resolved) if kind == "secret" else resolved
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "kind": kind,
                    "configured": bool(resolved),
                    "source": source,
                    "preview": preview,
                }
            )
        return rows

    def _save(self) -> None:
        """Best-effort — never raises, so a disk hiccup can't break a
        settings save that otherwise succeeded in memory."""
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
        if isinstance(raw, dict):
            self._data = {k: v for k, v in raw.items() if k in _KNOWN_KEYS and isinstance(v, str)}


_store: SettingsStore | None = None


def get_settings_store() -> SettingsStore:
    global _store
    if _store is None:
        _store = SettingsStore()
    return _store
