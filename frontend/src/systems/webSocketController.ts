"use client";

import type { WebSocketMessage } from "@/lib/types";
import { useGameStore } from "@/stores/gameStore";

// Ported pattern from claude-office's webSocketController.ts: thin transport
// layer that owns the connection lifecycle and dispatches parsed messages
// into the store. No reconnect backoff tuning yet (Phase 2 scope is "prove
// the pipeline works", not production hardening).
export function connectSession(sessionId: string, baseUrl = "ws://localhost:8010"): () => void {
  const ws = new WebSocket(`${baseUrl}/ws/${sessionId}`);

  ws.onopen = () => useGameStore.getState().setConnected(true);
  ws.onclose = () => useGameStore.getState().setConnected(false);
  ws.onerror = () => useGameStore.getState().setConnected(false);

  ws.onmessage = (event) => {
    let msg: WebSocketMessage;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    if (msg.type === "state_update" && msg.state) {
      useGameStore.getState().processBackendState(msg.state);
    }
  };

  return () => ws.close();
}
