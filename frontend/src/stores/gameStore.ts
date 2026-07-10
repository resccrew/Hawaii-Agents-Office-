"use client";

import { create } from "zustand";
import type { GameState } from "@/lib/types";
import { createDevSlice, type DevSlice } from "./slices/devSlice";
import { createLeadSlice, type LeadSlice } from "./slices/leadSlice";
import { createStudioSlice, type StudioSlice } from "./slices/studioSlice";

export type GameStore = DevSlice &
  LeadSlice &
  StudioSlice & {
    processBackendState: (state: GameState) => void;
  };

// Composition root (ported pattern from claude-office's gameStore.ts slice
// composition). processBackendState is the single entry point WS snapshots
// go through; each slice's own reconciler decides what to preserve vs.
// overwrite so in-flight animations never get clobbered by a WS tick.
export const useGameStore = create<GameStore>()((set, get, api) => ({
  ...createDevSlice(set, get, api),
  ...createLeadSlice(set, get, api),
  ...createStudioSlice(set, get, api),

  processBackendState: (state) => {
    get().reconcileDevs(state.devs);
    get().updateLead(state.lead);
    get().applyStudioMeta(state);
  },
}));

export const selectDevs = (s: GameStore) => s.devs;
export const selectLead = (s: GameStore) => s.lead;
export const selectIsConnected = (s: GameStore) => s.isConnected;
export const selectConversation = (s: GameStore) => s.conversation;
export const selectSessionId = (s: GameStore) => s.sessionId;
export const selectDepartmentId = (s: GameStore) => s.departmentId;
