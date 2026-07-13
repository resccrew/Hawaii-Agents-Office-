"""ConversationalProvider backed by Google's Gemini API (generateContent /
streamGenerateContent) — lets an agent's "brain" be Gemini instead of
Claude. Same stateless-history-replay design as openai_provider.py: no
native session resumption, so the persisted conversation log is resent as
context on every call (see providers/_history.py).

Not wired to the studio-ops MCP tools yet — see openai_provider.py's
docstring, same caveat applies here (chat/coordination works, agent-side
tool calls into studio_create_task etc. do not, yet).
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import AsyncIterator

import httpx

from app.core.attachments import SavedAttachment
from app.core.settings_store import get_settings_store
from app.services.providers._attachments import augment_with_text_attachments, image_attachments
from app.services.providers._history import load_history
from app.services.providers.base import ConversationalProvider, ProviderChunk, ProviderError, SpawnResult

DEFAULT_MODEL = "gemini-2.0-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _model() -> str:
    return get_settings_store().get("gemini_model") or DEFAULT_MODEL


def _api_key() -> str:
    key = get_settings_store().get("gemini_api_key")
    if not key:
        raise ProviderError(
            "Gemini provider not configured — set an API key in Settings "
            "(or STUDIO_OPS_GEMINI_API_KEY) to enable it."
        )
    return key


def _contents_for(
    history: list[tuple[str, str]],
    new_message: str,
    images: list[SavedAttachment],
) -> list[dict[str, object]]:
    # Gemini's roles are "user" / "model", not "user" / "assistant".
    contents = [
        {"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]}
        for role, text in history
    ]
    parts: list[dict[str, object]] = [{"text": new_message}]
    for img in images:
        b64 = base64.b64encode(img.path.read_bytes()).decode("ascii")
        parts.append({"inline_data": {"mime_type": img.mime_type, "data": b64}})
    contents.append({"role": "user", "parts": parts})
    return contents


class GeminiProvider(ConversationalProvider):
    name = "gemini"

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
        session_id = str(uuid.uuid4())
        text = ""
        async for chunk in self.send(
            external_session_id=session_id, workspace_dir=workspace_dir, message=initial_prompt
        ):
            if chunk.kind == "text_delta":
                text = chunk.text
            elif chunk.kind == "error":
                raise ProviderError(chunk.text)
        return SpawnResult(external_session_id=session_id, first_response=text)

    async def send(
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
        # No Claude-Code-style --model/--effort equivalent here — this
        # provider's model comes from Settings (gemini_model), effort has
        # no analog for the plain generateContent API. Accepted for
        # ConversationalProvider interface parity, intentionally unused.
        del model, effort
        message = augment_with_text_attachments(message, attachments)
        history = load_history(external_session_id)
        payload = {"contents": _contents_for(history, message, image_attachments(attachments))}
        url = f"{API_BASE}/{_model()}:streamGenerateContent"
        params = {"alt": "sse", "key": _api_key()}

        accumulated = ""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, params=params, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise ProviderError(
                            f"Gemini API error {resp.status_code}: {body.decode(errors='replace')[:400]}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if not data:
                            continue
                        try:
                            obj = json.loads(data)
                        except ValueError:
                            continue
                        candidates = obj.get("candidates") or []
                        if not candidates:
                            continue
                        parts = candidates[0].get("content", {}).get("parts", [])
                        piece = "".join(p.get("text", "") for p in parts)
                        if piece:
                            accumulated += piece
                            yield ProviderChunk(kind="text_delta", text=accumulated, raw=obj)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gemini request failed: {exc}") from exc

        yield ProviderChunk(kind="turn_complete", text=accumulated)
