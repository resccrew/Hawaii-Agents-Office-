"use client";

import { useChatStore } from "@/stores/chatStore";
import { getHttpBase, getWsBase } from "./backendUrl";
import { connectWithRetry } from "./reconnectingWebSocket";

// Manages /ws/chat/{session_id} lifecycle — kept separate from
// webSocketController.ts (observation channel) per the plan, since chat
// framing/backpressure must never compete with state_update broadcast.
// Bugfix: now auto-reconnects instead of going silently dead on a drop.
export function connectChat(sessionId: string, baseUrl = getWsBase()): () => void {
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

export interface ChatAttachmentUpload {
  filename: string;
  mimeType: string;
  dataBase64: string; // raw base64, no "data:...;base64," prefix
}

/** Reads a File into a raw-base64 payload ready for the chat send API.
 * FileReader's readAsDataURL is the simplest cross-browser way to get
 * base64 out of a File — its result is always "data:<mime>;base64,<data>",
 * so the prefix up to the first comma is just stripped. */
export function fileToAttachment(file: File): Promise<ChatAttachmentUpload> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      resolve({
        filename: file.name,
        mimeType: file.type || "application/octet-stream",
        dataBase64: comma >= 0 ? result.slice(comma + 1) : result,
      });
    };
    reader.onerror = () => reject(reader.error ?? new Error("failed to read file"));
    reader.readAsDataURL(file);
  });
}

// `model`/`effort` are Claude-only (`claude -p --model --effort`), chosen
// per-message from ChatWindow.tsx's selector — the backend ignores them
// for any other provider (see chat_bridge.py).
export async function sendChatMessage(
  sessionId: string,
  text: string,
  options: {
    model?: string;
    effort?: string;
    attachments?: ChatAttachmentUpload[];
    apiBase?: string;
  } = {},
): Promise<void> {
  const { model, effort, attachments = [], apiBase = getHttpBase() } = options;
  useChatStore.getState().appendUserMessage(
    sessionId,
    text,
    attachments.map((a) => a.filename),
  );
  await fetch(`${apiBase}/api/v1/chat/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      model: model || undefined,
      effort: effort || undefined,
      attachments: attachments.map((a) => ({
        filename: a.filename,
        mime_type: a.mimeType,
        data_base64: a.dataBase64,
      })),
    }),
  });
}
