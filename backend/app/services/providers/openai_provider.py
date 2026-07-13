"""ConversationalProvider backed by OpenAI's Chat Completions API — lets an
agent's "brain" be GPT instead of Claude. No native session/--resume
mechanism the way `claude -p` has, so conversation memory is reconstructed
on every call from the persisted conversation log (see providers/_history.py)
rather than kept server-side.

Not wired to the studio-ops MCP tools yet (mcp_config_path/permission_mode
are accepted for interface parity with ConversationalProvider but unused)
— a GPT-backed agent can chat and be coordinated via chat, but can't yet
call studio_create_task/studio_spawn_agent itself the way a Claude agent
can. Real tool-calling parity would mean bridging OpenAI's function-calling
format to the same MCP server, which is future work.
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

DEFAULT_MODEL = "gpt-4o-mini"
API_URL = "https://api.openai.com/v1/chat/completions"


def _model() -> str:
    return get_settings_store().get("openai_model") or DEFAULT_MODEL


def _api_key() -> str:
    key = get_settings_store().get("openai_api_key")
    if not key:
        raise ProviderError(
            "OpenAI provider not configured — set an API key in Settings "
            "(or STUDIO_OPS_OPENAI_API_KEY) to enable it."
        )
    return key


def _messages_for(
    history: list[tuple[str, str]],
    new_message: str,
    images: list[SavedAttachment],
) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = [{"role": role, "content": text} for role, text in history]
    if images:
        # Multimodal content array — only used for the message that
        # actually carries images; every other turn stays a plain string
        # (simpler, and matches what's already durably in conversation
        # history, which only ever stores text).
        content: list[dict[str, object]] = [{"type": "text", "text": new_message}]
        for img in images:
            b64 = base64.b64encode(img.path.read_bytes()).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{img.mime_type};base64,{b64}"}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": new_message})
    return messages


class OpenAIProvider(ConversationalProvider):
    name = "openai"

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
        # provider's model comes from Settings (openai_model). Accepted for
        # ConversationalProvider interface parity, intentionally unused.
        del model, effort
        message = augment_with_text_attachments(message, attachments)
        history = load_history(external_session_id)
        payload = {
            "model": _model(),
            "messages": _messages_for(history, message, image_attachments(attachments)),
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}

        accumulated = ""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", API_URL, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise ProviderError(
                            f"OpenAI API error {resp.status_code}: {body.decode(errors='replace')[:400]}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except ValueError:
                            continue
                        delta = obj.get("choices", [{}])[0].get("delta", {})
                        piece = delta.get("content")
                        if piece:
                            accumulated += piece
                            yield ProviderChunk(kind="text_delta", text=accumulated, raw=obj)
        except httpx.HTTPError as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc

        yield ProviderChunk(kind="turn_complete", text=accumulated)
