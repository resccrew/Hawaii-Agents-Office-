"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

// General, frontend-only app settings (distinct from the backend-persisted
// provider API keys in api.ts's getSettings/updateSettings) — things that
// only ever matter to this browser tab, so localStorage is the right home
// for them rather than a server round-trip.
export interface UiSettings {
  backendHttpUrl: string;
  defaultDepartment: string;
  reduceMotion: boolean;
  theme: "hawaii" | "terminal";
}

interface UiSettingsStore extends UiSettings {
  setBackendHttpUrl: (url: string) => void;
  setDefaultDepartment: (dept: string) => void;
  setReduceMotion: (on: boolean) => void;
  setTheme: (theme: "hawaii" | "terminal") => void;
  reset: () => void;
}

export const DEFAULT_UI_SETTINGS: UiSettings = {
  backendHttpUrl: "http://localhost:8010",
  defaultDepartment: "Engineering",
  reduceMotion: false,
  theme: "hawaii",
};

export const useUiSettingsStore = create<UiSettingsStore>()(
  persist(
    (set) => ({
      ...DEFAULT_UI_SETTINGS,
      setBackendHttpUrl: (url) =>
        set({ backendHttpUrl: url.trim().replace(/\/+$/, "") || DEFAULT_UI_SETTINGS.backendHttpUrl }),
      setDefaultDepartment: (defaultDepartment) => set({ defaultDepartment }),
      setReduceMotion: (reduceMotion) => set({ reduceMotion }),
      setTheme: (theme) => set({ theme }),
      reset: () => set(DEFAULT_UI_SETTINGS),
    }),
    { name: "studio-ops-ui-settings" },
  ),
);
