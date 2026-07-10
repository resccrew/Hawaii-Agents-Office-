import type { StateCreator } from "zustand";
import type { Lead } from "@/lib/types";
import type { LeadAnimationState } from "./types";
import { PRODUCER_SPOT } from "@/systems/layout";

export interface LeadSlice {
  lead: LeadAnimationState;
  updateLead: (backendLead: Lead) => void;
}

// Producer stands on the round rug near the Aloha Brew bar — open floor,
// no furniture obstacle, matches the office background image.
export const initialLeadState: { lead: LeadAnimationState } = {
  lead: {
    backendState: "idle",
    phase: "idle",
    position: PRODUCER_SPOT,
    currentTask: null,
    chatAvailable: true,
    role: null,
    name: null,
  },
};

export const createLeadSlice: StateCreator<LeadSlice, [], [], LeadSlice> = (set) => ({
  ...initialLeadState,
  updateLead: (backendLead) =>
    set((state) => ({
      lead: {
        ...state.lead,
        backendState: backendLead.state,
        phase:
          backendLead.state === "delegating"
            ? "delegating"
            : backendLead.state === "idle"
              ? "idle"
              : "working",
        currentTask: backendLead.currentTask ?? state.lead.currentTask,
        chatAvailable: backendLead.chatAvailable,
        role: backendLead.role ?? null,
        name: backendLead.name ?? null,
      },
    })),
});
