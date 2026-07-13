"use client";

import { create } from "zustand";
import type { Lead, Dev } from "@/lib/types";

// Separate from gameStore on purpose: gameStore models exactly one connected
// session (single lead/devs/studio). A department's /ws/room/{id} channel
// fans out state_update envelopes for however many sessions are live in that
// department at once, so this store keys everything by session_id instead.
export interface RoomSessionState {
  sessionId: string;
  lead: Lead;
  // Task-tool subagents spawned WITHIN this session (SUBAGENT_START/STOP —
  // see state_machine.py's _apply_agent). Rendered as cats near their
  // owner Lead — see CatCapsule.tsx / catMovement.ts.
  devs: Dev[];
  lastUpdated: string;
}

interface RoomStore {
  sessions: Map<string, RoomSessionState>;
  upsertSession: (sessionId: string, lead: Lead, devs: Dev[], lastUpdated: string) => void;
  removeSession: (sessionId: string) => void;
  clear: () => void;
}

export const useRoomStore = create<RoomStore>()((set) => ({
  sessions: new Map(),

  upsertSession: (sessionId, lead, devs, lastUpdated) =>
    set((state) => {
      const next = new Map(state.sessions);
      next.set(sessionId, { sessionId, lead, devs, lastUpdated });
      return { sessions: next };
    }),

  removeSession: (sessionId) =>
    set((state) => {
      if (!state.sessions.has(sessionId)) return state;
      const next = new Map(state.sessions);
      next.delete(sessionId);
      return { sessions: next };
    }),

  clear: () => set({ sessions: new Map() }),
}));

export const selectRoomSessions = (s: RoomStore) => s.sessions;
