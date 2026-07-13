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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.attachments import SavedAttachment


class ProviderError(RuntimeError):
    """Raised by any provider implementation (Claude, OpenAI, Gemini,
    Ollama, ...) when a call fails — bad/missing API key, network error,
    model error, timeout. The one exception type chat_bridge.py and
    agent_spawner.py need to catch regardless of which provider is behind
    a given agent, so adding a new provider never means also touching the
    orchestration layer's error handling."""


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
        model: str | None = None,
        effort: str | None = None,
    ) -> SpawnResult:
        """Start a brand-new session with the first prompt. Returns the
        provider's own session id (for future resume) and its first reply.

        `model`/`effort` (Claude-specific today — `claude -p --model
        --effort`): a provider that has no equivalent concept accepts and
        ignores them, same as mcp_config_path/permission_mode already are
        for non-Claude providers."""

    @abstractmethod
    def send(
        self,
        *,
        external_session_id: str,
        workspace_dir: str,
        message: str,
        mcp_config_path: str | None = None,
        permission_mode: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        attachments: list[SavedAttachment] | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        """Continue an existing session with a new message. `model`/`effort`
        are picked fresh per call (see ChatWindow.tsx's selector) — Claude
        Code has no notion of "this session is locked to a model", each
        `claude -p --resume` invocation is free to change it turn to turn.

        `attachments` (see app/core/attachments.py): files attached to THIS
        turn only — text content gets inlined into the prompt/message by
        whichever provider handles it (identical across all four), images
        are handled per-provider (Claude: reference the saved path, its own
        Read tool views images; OpenAI/Gemini/Ollama: base64'd into their
        own multimodal content format)."""


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
