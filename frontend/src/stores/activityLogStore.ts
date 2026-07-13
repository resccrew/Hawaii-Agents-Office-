"use client";

import { create } from "zustand";
import type { HistoryEntry } from "@/lib/types";

// Studio-wide activity feed — port of claude-office's EventLog panel,
// adapted to our multi-agent registry instead of a single observed session.
// Every agent's StateMachine already keeps a capped `history` array
// server-side (event_processor.py broadcasts it in full on every
// state_update); this just diffs each broadcast against what's already
// been ingested so the log grows incrementally instead of re-adding the
// same 200 entries on every tick.
export interface LogEntry extends HistoryEntry {
  agentName: string | null;
}

interface ActivityLogStore {
  entries: LogEntry[];
  ingest: (sessionId: string, agentName: string | null, history: HistoryEntry[]) => void;
  clear: () => void;
}

const MAX_LOG_ENTRIES = 300;
// Per-session count of history entries already ingested — module-level
// (not store state) since it's bookkeeping, not something any component
// renders; mirrors officeMovement.ts's memo pattern.
const seenCount = new Map<string, number>();

export const useActivityLogStore = create<ActivityLogStore>()((set, get) => ({
  entries: [],

  ingest: (sessionId, agentName, history) => {
    const prevCount = seenCount.get(sessionId) ?? 0;
    if (history.length <= prevCount) {
      // Backend's array shrank or is unchanged (e.g. its own 200-entry cap
      // rolled over) — resync the count, nothing new to append.
      seenCount.set(sessionId, history.length);
      return;
    }
    const fresh = history.slice(prevCount).map((h) => ({ ...h, agentName }));
    seenCount.set(sessionId, history.length);

    const merged = [...get().entries, ...fresh];
    const entries = merged.length > MAX_LOG_ENTRIES ? merged.slice(merged.length - MAX_LOG_ENTRIES) : merged;
    set({ entries });
  },

  clear: () => {
    seenCount.clear();
    set({ entries: [] });
  },
}));

export const selectLogEntries = (s: ActivityLogStore) => s.entries;
