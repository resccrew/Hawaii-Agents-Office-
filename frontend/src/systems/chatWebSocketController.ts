"use client";

import { useChatStore } from "@/stores/chatStore";
import { connectWithRetry } from "./reconnectingWebSocket";

// Manages /ws/chat/{session_id} lifecycle — kept separate from
// webSocketController.ts (observation channel) per the plan, since chat
// framing/backpressure must never compete with state_update broadcast.
// Bugfix: now auto-reconnects instead of going silently dead on a drop.
export function connectChat(sessionId: string, baseUrl = "ws://localhost:8010"): () => void {
  return connectWithRetry(`${baseUrl}/ws/chat/${sessionId}`, {
    onMessage: (event) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }
      useChatStore.getState().handleChatWsMessage(sessionId, msg);
    },
  });
}

export async function sendChatMessage(
  sessionId: string,
  text: string,
  apiBase = "http://localhost:8010",
): Promise<void> {
  useChatStore.getState().appendUserMessage(sessionId, text);
  await fetch(`${apiBase}/api/v1/chat/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}
