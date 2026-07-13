"""ConversationalProvider backed by a local Ollama server — lets an agent's
"brain" be a locally-hosted model instead of Claude. Same stateless-history-
replay design as openai_provider.py: Ollama's /api/chat is stateless per
call, so the persisted conversation log is resent as context every turn
(see providers/_history.py).

No API key (it's local), but very much "configured or not" in the same
spirit — a clear ProviderError if the server isn't reachable, rather than
a generic connection-refused traceback.

Not wired to the studio-ops MCP tools yet — see openai_provider.py's
docstring, same caveat applies here.
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

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1"


def _base_url() -> str:
    return (get_settings_store().get("ollama_base_url") or DEFAULT_BASE_URL).rstrip("/")


def _model() -> str:
    return get_settings_store().get("ollama_model") or DEFAULT_MODEL


def _messages_for(
    history: list[tuple[str, str]],
    new_message: str,
    images: list[SavedAttachment],
) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = [{"role": role, "content": text} for role, text in history]
    user_msg: dict[str, object] = {"role": "user", "content": new_message}
    if images:
        # Ollama's /api/chat takes raw base64 (no data: URI prefix) in a
        # per-message "images" array — only vision-capable local models do
        # anything useful with it; others just ignore the field.
        user_msg["images"] = [base64.b64encode(img.path.read_bytes()).decode("ascii") for img in images]
    messages.append(user_msg)
    return messages


class OllamaProvider(ConversationalProvider):
    name = "ollama"

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
        # provider's model comes from Settings (ollama_model). Accepted for
        # ConversationalProvider interface parity, intentionally unused.
        del model, effort
        message = augment_with_text_attachments(message, attachments)
        history = load_history(external_session_id)
        payload = {
            "model": _model(),
            "messages": _messages_for(history, message, image_attachments(attachments)),
            "stream": True,
        }
        url = f"{_base_url()}/api/chat"

        accumulated = ""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise ProviderError(
                            f"Ollama API error {resp.status_code}: {body.decode(errors='replace')[:400]}"
                        )
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            continue
                        if obj.get("error"):
                            raise ProviderError(f"Ollama error: {obj['error']}")
                        piece = obj.get("message", {}).get("content", "")
                        if piece:
                            accumulated += piece
                            yield ProviderChunk(kind="text_delta", text=accumulated, raw=obj)
                        if obj.get("done"):
                            break
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Ollama not reachable at {_base_url()} — is `ollama serve` running? "
                "(set the base URL in Settings, or STUDIO_OPS_OLLAMA_BASE_URL)"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc

        yield ProviderChunk(kind="turn_complete", text=accumulated)
