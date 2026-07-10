"""WebSocket fan-out, ported from claude-office's connection_manager.py.

Three channel kinds, matching the reference project's three WS endpoints:
per-session state (`/ws/{session_id}`), overview (`/ws/overview`), and
per-department merged rooms (`/ws/room/{department_id}`). Phase 3 adds a
fourth, `/ws/chat/{session_id}`, kept on a separate registry (`chat_channels`)
so chat message framing never competes with observation broadcast traffic.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.session_channels: dict[str, set[WebSocket]] = defaultdict(set)
        self.overview_channels: set[WebSocket] = set()
        self.room_channels: dict[str, set[WebSocket]] = defaultdict(set)
        self.chat_channels: dict[str, set[WebSocket]] = defaultdict(set)
        # Phase 6: shared task board, keyed by department_id — separate
        # from room_channels (observation) so task CRUD broadcasts never
        # compete with state_update traffic, same reasoning as chat_channels.
        self.task_channels: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect_session(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.session_channels[session_id].add(ws)

    def disconnect_session(self, session_id: str, ws: WebSocket) -> None:
        self.session_channels[session_id].discard(ws)
        if not self.session_channels[session_id]:
            del self.session_channels[session_id]

    async def connect_overview(self, ws: WebSocket) -> None:
        await ws.accept()
        self.overview_channels.add(ws)

    def disconnect_overview(self, ws: WebSocket) -> None:
        self.overview_channels.discard(ws)

    async def connect_room(self, room_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.room_channels[room_id].add(ws)

    def disconnect_room(self, room_id: str, ws: WebSocket) -> None:
        self.room_channels[room_id].discard(ws)
        if not self.room_channels[room_id]:
            del self.room_channels[room_id]

    async def connect_chat(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.chat_channels[session_id].add(ws)

    def disconnect_chat(self, session_id: str, ws: WebSocket) -> None:
        self.chat_channels[session_id].discard(ws)
        if not self.chat_channels[session_id]:
            del self.chat_channels[session_id]

    async def connect_task(self, department_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.task_channels[department_id].add(ws)

    def disconnect_task(self, department_id: str, ws: WebSocket) -> None:
        self.task_channels[department_id].discard(ws)
        if not self.task_channels[department_id]:
            del self.task_channels[department_id]

    async def broadcast_task(self, department_id: str, message: dict) -> None:
        await self._broadcast(self.task_channels.get(department_id, set()), message)

    async def broadcast_session(self, session_id: str, message: dict) -> None:
        await self._broadcast(self.session_channels.get(session_id, set()), message)

    async def broadcast_overview(self, message: dict) -> None:
        await self._broadcast(self.overview_channels, message)

    async def broadcast_room(self, room_id: str, message: dict) -> None:
        await self._broadcast(self.room_channels.get(room_id, set()), message)

    async def broadcast_chat(self, session_id: str, message: dict) -> None:
        await self._broadcast(self.chat_channels.get(session_id, set()), message)

    @staticmethod
    async def _broadcast(sockets: set[WebSocket], message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            sockets.discard(ws)


_manager: ConnectionManager | None = None


def get_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
