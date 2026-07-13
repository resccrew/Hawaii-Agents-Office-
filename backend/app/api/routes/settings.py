"""Settings panel backend — GET/PUT for provider API keys and local
endpoints (app/core/settings_store.py), plus a model-listing proxy so the
Settings UI can offer a real dropdown of models instead of a guessed
free-text field. Deliberately tiny: no auth, no per-user scoping — this
mirrors every other piece of studio-ops state (tasks, agents,
conversations), which all assume a single trusted local user running the
whole stack on their own machine."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.settings_store import get_settings_store

router = APIRouter()

# Shown when a live catalog can't be fetched (no key yet, or the API call
# itself failed) — a reasonable starting point, not an authoritative or
# exhaustive list. The live fetch (once a key is saved) is what actually
# drives the dropdown day to day.
OPENAI_FALLBACK_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o3-mini"]
GEMINI_FALLBACK_MODELS = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"]


class UpdateSettingsRequest(BaseModel):
    values: dict[str, str]


@router.get("/settings")
async def get_settings() -> list[dict]:
    return get_settings_store().snapshot_masked()


@router.put("/settings")
async def update_settings(payload: UpdateSettingsRequest) -> list[dict]:
    get_settings_store().set_many(payload.values)
    return get_settings_store().snapshot_masked()


async def _list_openai_models() -> dict:
    key = get_settings_store().get("openai_api_key")
    if not key:
        return {"models": OPENAI_FALLBACK_MODELS, "source": "fallback"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"}
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        return {"models": OPENAI_FALLBACK_MODELS, "source": "fallback"}
    ids = [m.get("id") for m in data.get("data", []) if isinstance(m.get("id"), str)]
    # Filter to chat-capable models — the raw catalog also lists embeddings,
    # TTS, moderation, etc. models that would just be noise in this picker.
    chat_ids = sorted(i for i in ids if i.startswith(("gpt-", "o1", "o3", "o4")))
    return {"models": chat_ids or OPENAI_FALLBACK_MODELS, "source": "live" if chat_ids else "fallback"}


async def _list_gemini_models() -> dict:
    key = get_settings_store().get("gemini_api_key")
    if not key:
        return {"models": GEMINI_FALLBACK_MODELS, "source": "fallback"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models", params={"key": key}
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        return {"models": GEMINI_FALLBACK_MODELS, "source": "fallback"}
    names = [
        m["name"].removeprefix("models/")
        for m in data.get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    return {"models": sorted(names) or GEMINI_FALLBACK_MODELS, "source": "live" if names else "fallback"}


async def _list_ollama_models() -> dict:
    base_url = (get_settings_store().get("ollama_base_url") or "http://localhost:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        # No sensible universal fallback for local models — the UI shows a
        # "couldn't reach ollama" hint and falls back to free text instead.
        return {"models": [], "source": "unreachable"}
    names = [m.get("name") for m in data.get("models", []) if isinstance(m.get("name"), str)]
    return {"models": sorted(names), "source": "live"}


_LISTERS = {
    "openai": _list_openai_models,
    "gemini": _list_gemini_models,
    "ollama": _list_ollama_models,
}


@router.get("/settings/models/{provider}")
async def list_models(provider: str) -> dict:
    lister = _LISTERS.get(provider)
    if lister is None:
        raise HTTPException(status_code=404, detail=f"no model catalog for provider: {provider}")
    return await lister()
