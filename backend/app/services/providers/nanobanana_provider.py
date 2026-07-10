from __future__ import annotations

import os

from app.services.providers.base import GenerativeProvider, ProviderChunk

API_KEY_ENV = "STUDIO_OPS_NANOBANANA_API_KEY"


class NanoBananaProvider(GenerativeProvider):
    """Stub for a Gemini-2.5-Flash-Image-class ("Nano Banana") generative
    provider — same shape used for the Phase 5 sprite generation the user
    ran manually (no MCP/API access was available in this environment
    then, either). Scaffolded per the plan's "inert without a key"
    requirement: `configured` gates every call so a missing key surfaces
    as a clear chat/tool error, not a crash or a silent no-op.
    """

    name = "nanobanana"

    @property
    def configured(self) -> bool:
        return bool(os.environ.get(API_KEY_ENV))

    async def generate(self, *, prompt: str, kind: str) -> ProviderChunk:
        if not self.configured:
            return ProviderChunk(
                kind="error",
                text=(
                    f"nanobanana provider not configured — set {API_KEY_ENV} "
                    "to enable image/video generation for agents."
                ),
            )
        # Real call would go here once a key is provided — e.g. a Gemini
        # image-generation API request. Deliberately not implemented
        # against a guessed API shape; wire this up once the user supplies
        # actual credentials and confirms which endpoint/SDK to target.
        return ProviderChunk(
            kind="error",
            text="nanobanana provider is configured but generate() is not yet implemented.",
        )
