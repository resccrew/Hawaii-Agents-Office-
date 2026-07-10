"use client";

import { useChatStore } from "@/stores/chatStore";

// Manages /ws/chat/{session_id} lifecycle — kept separate from
// webSocketController.ts (observation channel) per the plan, since chat
// framing/backpressure must never compete with state_update broadcast.
export function connectChat(sessionId: string, baseUrl = "ws://localhost:8010"): () => void {
  const ws = new WebSocket(`${baseUrl}/ws/chat/${sessionId}`);

  ws.onmessage = (event) => {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    useChatStore.getState().handleChatWsMessage(sessionId, msg);
  };

  return () => ws.close();
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
