import type { StateCreator } from "zustand";
import type { Dev } from "@/lib/types";
import type { DevAnimationState } from "./types";
import { phaseForDevState } from "@/machines/devMachine";
import { gridSlot, pathToSpot, ENTRANCE_SPOT } from "@/systems/layout";

export interface DevSlice {
  devs: Map<string, DevAnimationState>;
  upsertDev: (backendDev: Dev, deskTarget: { x: number; y: number }) => void;
  removeDev: (id: string) => void;
  reconcileDevs: (backendDevs: Dev[]) => void;
}

export const initialDevState = { devs: new Map<string, DevAnimationState>() };

export const createDevSlice: StateCreator<DevSlice, [], [], DevSlice> = (set, get) => ({
  ...initialDevState,

  upsertDev: (backendDev, deskTarget) =>
    set((state) => {
      const next = new Map(state.devs);
      const existing = next.get(backendDev.id);
      // New dev: spawn at the entrance and compute an A*-routed path to
      // their desk, so they visibly walk around furniture instead of
      // teleporting or cutting through it. Existing devs keep whatever
      // position/path they already have (arrival animation runs once).
      const position = existing?.position ?? ENTRANCE_SPOT;
      const path = existing ? existing.path : pathToSpot(deskTarget);
      next.set(backendDev.id, {
        id: backendDev.id,
        name: backendDev.name ?? existing?.name ?? null,
        color: backendDev.color,
        number: backendDev.number,
        role: backendDev.role,
        backendState: backendDev.state,
        phase: phaseForDevState(backendDev.state),
        position,
        targetPosition: deskTarget,
        path,
        currentTask: backendDev.currentTask ?? existing?.currentTask ?? null,
        chatAvailable: backendDev.chatAvailable,
      });
      return { devs: next };
    }),

  removeDev: (id) =>
    set((state) => {
      const next = new Map(state.devs);
      next.delete(id);
      return { devs: next };
    }),

  // processBackendState reconciler (ported pattern from claude-office's
  // gameStore.processBackendState): merge backend snapshot into animation
  // state without discarding position/phase for devs that are still present.
  reconcileDevs: (backendDevs) => {
    const backendIds = new Set(backendDevs.map((d) => d.id));
    for (const id of Array.from(get().devs.keys())) {
      if (!backendIds.has(id)) get().removeDev(id);
    }
    backendDevs.forEach((backendDev, index) => {
      get().upsertDev(backendDev, gridSlot(index));
    });
  },
});
