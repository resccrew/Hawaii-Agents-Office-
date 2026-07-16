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
  // Multiple chat windows open at once. Array order IS the z-order: the
  // last entry is the front-most/focused window. openPanel appends (or
  // re-focuses an already-open one); focusPanel moves a window to the end.
  openSessions: string[];
  openPanel: (sessionId: string) => void;
  closePanel: (sessionId: string) => void;
  focusPanel: (sessionId: string) => void;
  appendUserMessage: (sessionId: string, text: string, attachmentNames?: string[]) => void;
  handleChatWsMessage: (sessionId: string, msg: Record<string, unknown>) => void;
}

// Separate store from gameStore (per plan: chat is not part of the
// deterministic scene-state snapshot — it's an append-only per-session log
// with its own connection/queue status, not something processBackendState
// should reconcile).
export const useChatStore = create<ChatStore>()((set, get) => ({
  sessions: new Map(),
  openSessions: [],

  openPanel: (sessionId) =>
    set((state) => ({
      // Already open → just bring to front; otherwise add on top.
      openSessions: [...state.openSessions.filter((id) => id !== sessionId), sessionId],
    })),
  closePanel: (sessionId) =>
    set((state) => ({ openSessions: state.openSessions.filter((id) => id !== sessionId) })),
  focusPanel: (sessionId) =>
    set((state) =>
      state.openSessions.at(-1) === sessionId
        ? state
        : { openSessions: [...state.openSessions.filter((id) => id !== sessionId), sessionId] },
    ),

  appendUserMessage: (sessionId, text, attachmentNames) =>
    set((state) => {
      const sessions = new Map(state.sessions);
      const existing = sessions.get(sessionId) ?? { messages: [], status: "idle" as const };
      // Mirrors chat_bridge.py's own "📎 filename" note on the persisted/
      // broadcast side — same format, so a live-typed message and one
      // recovered via chat_history replay after a reconnect read identically.
      const displayText =
        attachmentNames && attachmentNames.length > 0
          ? `${text}${text ? "\n\n" : ""}📎 ${attachmentNames.join(", ")}`
          : text;
      sessions.set(sessionId, {
        messages: [...existing.messages, { id: crypto.randomUUID(), role: "user", text: displayText }],
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
      case "chat_history": {
        // Sent once by the backend right after a chat WS connects, replaying
        // sm.conversation (persisted to disk — see conversation_store.py) so
        // a fresh connection never starts blank: first time opening this
        // agent's chat, reconnecting after a network blip, or reconnecting
        // after a backend restart all used to silently show nothing for
        // everything that already happened. Backend is authoritative for
        // anything it has recorded, but a turn already streaming in on THIS
        // connection can't be in that snapshot yet (its response_text isn't
        // recorded until the turn completes) — keep any local message still
        // mid-stream so a reconnect mid-reply doesn't cut it off.
        const inFlight = existing.messages.filter((m) => m.status === "streaming");
        const raw = Array.isArray(msg.messages) ? (msg.messages as Record<string, unknown>[]) : [];
        const history: ChatLogMessage[] = raw.map((m) => ({
          id: String(m.id ?? crypto.randomUUID()),
          role: m.role === "user" || m.role === "assistant" ? m.role : "system",
          text: String(m.text ?? ""),
        }));
        // Receiving history means the socket is connected and healthy again,
        // so clear any stale "error" left over from the drop that triggered
        // this reconnect (otherwise the red "connection error" banner sticks
        // forever even though the agent is replying fine). Preserve
        // "streaming" if a reply is still mid-flight on this connection.
        const recoveredStatus: ChatTurnStatus = inFlight.length > 0 ? "streaming" : "idle";
        sessions.set(sessionId, { messages: [...history, ...inFlight], status: recoveredStatus });
        set({ sessions });
        return;
      }
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
export const selectOpenSessions = (state: ChatStore) => state.openSessions;
