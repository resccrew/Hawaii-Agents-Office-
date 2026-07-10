import type { StateCreator } from "zustand";
import type { GameState } from "@/lib/types";

export interface StudioSlice {
  sessionId: string;
  departmentId: string | null;
  deskCount: number;
  contextUtilization: number;
  conversation: GameState["conversation"];
  isConnected: boolean;
  setConnected: (connected: boolean) => void;
  applyStudioMeta: (state: GameState) => void;
}

export const initialStudioState = {
  sessionId: "",
  departmentId: null as string | null,
  deskCount: 8,
  contextUtilization: 0,
  conversation: [] as GameState["conversation"],
  isConnected: false,
};

export const createStudioSlice: StateCreator<StudioSlice, [], [], StudioSlice> = (set) => ({
  ...initialStudioState,
  setConnected: (connected) => set({ isConnected: connected }),
  applyStudioMeta: (state) =>
    set({
      sessionId: state.sessionId,
      departmentId: state.departmentId ?? null,
      deskCount: state.studio.deskCount,
      contextUtilization: state.studio.contextUtilization,
      conversation: state.conversation,
    }),
});
