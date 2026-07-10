"""Provider interface — every "neural network" Studio Ops can spawn as an
agent implements one of these two shapes. Conversational providers (Claude,
eventually GPT) have persistent turn-by-turn sessions and plug into the
existing chat_bridge.py/ChatPanel.tsx pipeline unchanged. Generative
providers (image/video) are one-shot: a prompt in, an artifact out, no
resumable session — they plug into the studio-ops MCP server's
generate_image/generate_video tools instead of the chat panel.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderChunk:
    kind: str  # "text_delta" | "turn_complete" | "error"
    text: str = ""
    raw: dict[str, Any] | None = None


@dataclass
class SpawnResult:
    external_session_id: str | None  # provider's own resumable id, if any
    first_response: str


class ConversationalProvider(ABC):
    """Turn-by-turn agents with a persistent session — Claude today,
    structurally ready for an OpenAI/GPT-Codex variant later (same
    contract, different subprocess/HTTP call underneath)."""

    name: str

    @abstractmethod
    async def spawn(
        self,
        *,
        workspace_dir: str,
        initial_prompt: str,
        mcp_config_path: str | None = None,
        permission_mode: str | None = None,
    ) -> SpawnResult:
        """Start a brand-new session with the first prompt. Returns the
        provider's own session id (for future resume) and its first reply."""

    @abstractmethod
    def send(
        self,
        *,
        external_session_id: str,
        workspace_dir: str,
        message: str,
        mcp_config_path: str | None = None,
        permission_mode: str | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        """Continue an existing session with a new message."""


class GenerativeProvider(ABC):
    """One-shot generation agents (image/video) — no persistent session.
    `configured` gates every call: Phase 6 ships this interface and a
    Nano-Banana-shaped stub, but no API key is present in this
    environment (same constraint noted for Phase 5 sprite generation), so
    calls must fail with a clear, catchable error rather than crash or
    hang."""

    name: str

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    async def generate(self, *, prompt: str, kind: str) -> ProviderChunk:
        """kind: "image" | "video". Returns a turn_complete chunk with a
        file path/URL in `text`, or an error chunk if not configured or
        the call fails."""
