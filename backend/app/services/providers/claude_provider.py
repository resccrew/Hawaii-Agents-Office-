from __future__ import annotations

from collections.abc import AsyncIterator

from app.core.attachments import SavedAttachment
from app.services import claude_cli_service
from app.services.providers._attachments import (
    augment_with_text_attachments,
    image_attachments,
    other_attachments,
)
from app.services.providers.base import ConversationalProvider, ProviderChunk, SpawnResult


class ClaudeProvider(ConversationalProvider):
    """Wraps claude_cli_service.py (Phase 3, proven end-to-end in
    test_chat_bridge.py) — this is the "reuse wholesale, don't rewrite"
    piece called out in the plan."""

    name = "claude"

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
        result = await claude_cli_service.spawn_new_session(
            initial_prompt,
            cwd=workspace_dir,
            mcp_config_path=mcp_config_path,
            permission_mode=permission_mode,
            model=model,
            effort=effort,
        )
        return SpawnResult(external_session_id=result.session_id, first_response=result.result_text)

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
        # Claude Code has a real filesystem + Read tool (which natively
        # views images, not just text) — the cheapest, most capable way to
        # hand it a file is to just tell it the absolute path rather than
        # inlining/encoding anything ourselves. Text attachments still get
        # inlined directly (saves it a Read round-trip for something this
        # small), same as every other provider.
        message = augment_with_text_attachments(message, attachments)
        for a in [*image_attachments(attachments), *other_attachments(attachments)]:
            message += f"\n\n[Attached file: {a.filename} ({a.mime_type}) saved at {a.path}]"

        async for chunk in claude_cli_service.send_headless_message(
            external_session_id,
            message,
            cwd=workspace_dir,
            mcp_config_path=mcp_config_path,
            permission_mode=permission_mode,
            model=model,
            effort=effort,
        ):
            yield ProviderChunk(kind=chunk.kind, text=chunk.text, raw=chunk.raw)
