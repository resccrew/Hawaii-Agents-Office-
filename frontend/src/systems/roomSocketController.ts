"use client";

import type { WebSocketMessage } from "@/lib/types";
import { useRoomStore } from "@/stores/roomStore";
import { useActivityLogStore } from "@/stores/activityLogStore";
import { wsUrlWithToken } from "./apiAuth";
import { getWsBase } from "./backendUrl";
import { connectWithRetry } from "./reconnectingWebSocket";

function handleRoomMessage(event: MessageEvent) {
  let msg: WebSocketMessage;
  try {
    msg = JSON.parse(event.data);
  } catch {
    return;
  }
  if (msg.type === "state_update" && msg.state && msg.session_id) {
    useRoomStore
      .getState()
      .upsertSession(msg.session_id, msg.state.lead, msg.state.devs ?? [], msg.state.lastUpdated);
    useActivityLogStore
      .getState()
      .ingest(msg.session_id, msg.state.lead.name ?? msg.state.lead.role ?? null, msg.state.history);
  } else if (msg.type === "session_deleted" && msg.session_id) {
    useRoomStore.getState().removeSession(msg.session_id);
  }
}

// Mirrors webSocketController.ts's connectSession, pointed at the
// department-merge channel instead of a single session. Backend sends an
// initial snapshot per live session in the department on connect (see
// websockets.py's ws_room) — otherwise the room rendered empty until each
// session's *next* event happened to fire, even when agents were already
// standing there.
export function connectRoom(departmentId: string, baseUrl = getWsBase()): () => void {
  useRoomStore.getState().clear();
  return connectWithRetry(() => wsUrlWithToken(`${baseUrl}/ws/room/${departmentId}`), {
    onMessage: handleRoomMessage,
  });
}

// Studio-wide variant: every live agent regardless of department, backed by
// /ws/overview (same initial-snapshot-on-connect treatment as ws_room).
// This is "all agents in one room" — connectRoom above stays scoped to a
// single department's desks, which turned out not to be what was wanted.
export function connectOverview(baseUrl = getWsBase()): () => void {
  useRoomStore.getState().clear();
  return connectWithRetry(() => wsUrlWithToken(`${baseUrl}/ws/overview`), { onMessage: handleRoomMessage });
}
