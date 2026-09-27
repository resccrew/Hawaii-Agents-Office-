from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import agents, chat, events, generate, git, memory, settings, tasks, terminal, websockets, workspaces
from app.core.agent_spawner import rehydrate_office
from app.core.autopilot import get_autopilot
from app.core.ceo import ensure_ceo
from app.core.chat_bridge import get_chat_bridge
from app.core.connection_manager import get_manager
from app.core.department_config import load_studio_config
from app.core.event_processor import get_processor
from app.core.terminal_registry import get_terminal_registry

STUDIO_TOML = Path(__file__).resolve().parent.parent / "studio.toml"

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Rehydrate the office first: re-render every already-registered agent
    # (persisted across restarts) so the room isn't empty on boot. Cheap and
    # synchronous — no subprocesses, just in-memory StateMachines + a
    # broadcast. Then auto-start the CEO in the BACKGROUND — spawn_agent()
    # blocks on a claude subprocess (seconds), and we must not hold up the
    # server from accepting requests (the CEO itself calls back into this
    # API via its studio_spawn_agent MCP tool, so the API has to be live).
    await rehydrate_office()

    # Auto-start the CEO, then hand the board to the Autopilot: once the CEO
    # is up, kickstart drives any tasks already sitting unfinished on the
    # board (left from a previous run, or added before the CEO finished
    # booting). Chained so kickstart can't run before there's a CEO to drive.
    async def _boot_studio() -> None:
        await ensure_ceo()
        await get_autopilot(get_manager(), get_processor(get_manager())).kickstart()

    ceo_task = asyncio.create_task(_boot_studio())
    try:
        yield
    finally:
        ceo_task.cancel()
        # Terminal panes are real long-lived child processes (shell/claude/
        # codex) with no persistence to resurrect them from — kill them on
        # shutdown so a `--reload` dev restart or app quit doesn't leak them
        # the way the Tauri sidecar itself used to before its own fix.
        get_terminal_registry().close_all()


def create_app() -> FastAPI:
    app = FastAPI(title="Hawaii Agents Office", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3010",
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    manager = get_manager()
    studio_config = load_studio_config(STUDIO_TOML) if STUDIO_TOML.exists() else None
    processor = get_processor(manager, studio_config)
    get_chat_bridge(manager, processor)
    # Install the Autopilot now (registers the task-board + chat-bridge hooks)
    # so it's live before the first request can create a task.
    get_autopilot(manager, processor)

    app.include_router(events.router, prefix="/api/v1")
    app.include_router(chat.rest_router, prefix="/api/v1")
    app.include_router(agents.router, prefix="/api/v1")
    app.include_router(generate.router, prefix="/api/v1")
    app.include_router(settings.router, prefix="/api/v1")
    app.include_router(git.router, prefix="/api/v1")
    app.include_router(memory.router, prefix="/api/v1")
    app.include_router(tasks.rest_router, prefix="/api/v1")
    app.include_router(workspaces.router, prefix="/api/v1")
    app.include_router(terminal.rest_router, prefix="/api/v1")
    app.include_router(websockets.router)
    app.include_router(chat.ws_router)
    app.include_router(tasks.ws_router)
    app.include_router(terminal.ws_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
