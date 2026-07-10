"""Generative-provider endpoint (Phase 6) — proxied by the studio-ops MCP
server's generate_image/generate_video tools. Kept as a plain REST call
(not streaming) since generative providers are one-shot: prompt in,
artifact out, no persistent session."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.providers import get_generative_provider

router = APIRouter()


class GenerateRequest(BaseModel):
    provider: str = "nanobanana"
    kind: str = "image"  # "image" | "video"
    prompt: str


class GenerateResponse(BaseModel):
    status: str  # "ok" | "error"
    text: str


@router.post("/generate", response_model=GenerateResponse)
async def generate(payload: GenerateRequest) -> GenerateResponse:
    provider = get_generative_provider(payload.provider)
    if provider is None:
        return GenerateResponse(status="error", text=f"unknown provider: {payload.provider}")

    chunk = await provider.generate(prompt=payload.prompt, kind=payload.kind)
    return GenerateResponse(status="error" if chunk.kind == "error" else "ok", text=chunk.text)
