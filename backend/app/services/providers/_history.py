"""Shared helper: reconstruct a provider-agnostic message list from a
session's persisted conversation (app.core.conversation_store). Unlike
`claude -p --resume`, plain chat-completion APIs (OpenAI, Gemini, Ollama)
have no server-side memory of their own — each call is stateless, so every
provider that isn't Claude needs to resend the whole prior conversation on
every turn instead."""

from __future__ import annotations

from app.core.conversation_store import get_conversation_store


def load_history(session_id: str) -> list[tuple[str, str]]:
    """Returns (role, text) pairs, role in {"user", "assistant"}. Only
    "chat"-sourced entries — the same filter /ws/chat's history replay uses
    (see chat.py) — since these providers are only ever driven through the
    chat-bridge path; a hook-observed interactive session's own turns
    (source="interactive") belong to a different conversation entirely."""
    entries = get_conversation_store().get(session_id)
    return [
        (e["role"], e["text"])
        for e in entries
        if e.get("source") == "chat" and e.get("role") in ("user", "assistant")
    ]
