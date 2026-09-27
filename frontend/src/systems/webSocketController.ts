"use client";

import type { WebSocketMessage } from "@/lib/types";
import { useGameStore } from "@/stores/gameStore";
import { wsUrlWithToken } from "./apiAuth";
import { getWsBase } from "./backendUrl";
import { connectWithRetry } from "./reconnectingWebSocket";

// Ported pattern from claude-office's webSocketController.ts: thin transport
// layer that owns the connection lifecycle and dispatches parsed messages
// into the store. Bugfix: now auto-reconnects (via connectWithRetry)
// instead of leaving the UI stuck on "disconnected" after any drop.
export function connectSession(sessionId: string, baseUrl = getWsBase()): () => void {
  return connectWithRetry(() => wsUrlWithToken(`${baseUrl}/ws/${sessionId}`), {
    onOpen: () => useGameStore.getState().setConnected(true),
    onClose: () => useGameStore.getState().setConnected(false),
    onMessage: (event) => {
      let msg: WebSocketMessage;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }
      if (msg.type === "state_update" && msg.state) {
        useGameStore.getState().processBackendState(msg.state);
      } else if (msg.type === "session_deleted") {
        useGameStore.getState().setConnected(false);
        useGameStore.getState().resetSession();
      }
    },
  });
}
