"use client";

import { create } from "zustand";

export type ChatTurnStatus = "idle" | "queued" | "streaming" | "error";

export interface ChatLogMessage {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  status?: ChatTurnStatus;
}

interface SessionChatState {
  messages: ChatLogMessage[];
  status: ChatTurnStatus;
}

interface ChatStore {
  sessions: Map<string, SessionChatState>;
  activeSessionId: string | null;
  openPanel: (sessionId: string) => void;
  closePanel: () => void;
  appendUserMessage: (sessionId: string, text: string) => void;
  handleChatWsMessage: (sessionId: string, msg: Record<string, unknown>) => void;
}

// Separate store from gameStore (per plan: chat is not part of the
// deterministic scene-state snapshot — it's an append-only per-session log
// with its own connection/queue status, not something processBackendState
// should reconcile).
export const useChatStore = create<ChatStore>()((set, get) => ({
  sessions: new Map(),
  activeSessionId: null,

  openPanel: (sessionId) => set({ activeSessionId: sessionId }),
  closePanel: () => set({ activeSessionId: null }),

  appendUserMessage: (sessionId, text) =>
    set((state) => {
      const sessions = new Map(state.sessions);
      const existing = sessions.get(sessionId) ?? { messages: [], status: "idle" as const };
      sessions.set(sessionId, {
        messages: [...existing.messages, { id: crypto.randomUUID(), role: "user", text }],
        status: existing.status,
      });
      return { sessions };
    }),

  handleChatWsMessage: (sessionId, msg) => {
    const sessions = new Map(get().sessions);
    const existing = sessions.get(sessionId) ?? { messages: [], status: "idle" as const };
    const messages = [...existing.messages];
    let status: ChatTurnStatus = existing.status;

    switch (msg.type) {
      case "chat_queued":
        status = "queued";
        messages.push({
          id: crypto.randomUUID(),
          role: "system",
          text: "queued — agent is busy with the interactive terminal",
        });
        break;
      case "chat_turn_started":
        status = "streaming";
        break;
      case "chat_delta":
        status = "streaming";
        // Replace-in-place the trailing assistant message for this turn,
        // since our backend sends full-text-so-far, not token deltas.
        if (messages.at(-1)?.role === "assistant" && messages.at(-1)?.status === "streaming") {
          messages[messages.length - 1] = {
            ...messages[messages.length - 1],
            text: String(msg.text ?? ""),
          };
        } else {
          messages.push({
            id: crypto.randomUUID(),
            role: "assistant",
            text: String(msg.text ?? ""),
            status: "streaming",
          });
        }
        break;
      case "chat_turn_complete":
        status = "idle";
        if (messages.at(-1)?.role === "assistant") {
          messages[messages.length - 1] = {
            ...messages[messages.length - 1],
            text: String(msg.text ?? ""),
            status: "idle",
          };
        }
        break;
      case "chat_error":
        status = "error";
        messages.push({
          id: crypto.randomUUID(),
          role: "system",
          text: `error: ${String(msg.message ?? "unknown")}`,
        });
        break;
    }

    sessions.set(sessionId, { messages, status });
    set({ sessions });
  },
}));

// Referentially-stable empty state: returning a fresh `{}` literal from a
// Zustand selector every render trips React's "getServerSnapshot should be
// cached" infinite-loop guard (useSyncExternalStore requires a stable
// reference when nothing changed).
const EMPTY_SESSION_STATE: SessionChatState = { messages: [], status: "idle" };

export const selectChatSession = (sessionId: string) => (state: ChatStore) =>
  state.sessions.get(sessionId) ?? EMPTY_SESSION_STATE;
export const selectActiveChatSessionId = (state: ChatStore) => state.activeSessionId;
