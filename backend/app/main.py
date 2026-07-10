from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import agents, chat, events, generate, tasks, websockets
from app.core.chat_bridge import get_chat_bridge
from app.core.connection_manager import get_manager
from app.core.department_config import load_studio_config
from app.core.event_processor import get_processor

STUDIO_TOML = Path(__file__).resolve().parent.parent / "studio.toml"


def create_app() -> FastAPI:
    app = FastAPI(title="Studio Ops", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3010"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    manager = get_manager()
    studio_config = load_studio_config(STUDIO_TOML) if STUDIO_TOML.exists() else None
    processor = get_processor(manager, studio_config)
    get_chat_bridge(manager, processor)

    app.include_router(events.router, prefix="/api/v1")
    app.include_router(chat.rest_router, prefix="/api/v1")
    app.include_router(agents.router, prefix="/api/v1")
    app.include_router(generate.router, prefix="/api/v1")
    app.include_router(tasks.rest_router, prefix="/api/v1")
    app.include_router(websockets.router)
    app.include_router(chat.ws_router)
    app.include_router(tasks.ws_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
