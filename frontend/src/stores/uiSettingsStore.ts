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
  // Desktop-native affordances (see systems/desktopBridge.ts) — frontend-only
  // preferences, same as the rest of this store; the actual notification/
  // tray/badge/hotkey plumbing lives in src-tauri and no-ops entirely when
  // this is running as a plain browser tab (no Tauri bridge).
  desktopNotificationsEnabled: boolean;
  desktopHotkey: string;
  // Set once the "a macOS permission dialog is about to appear" notice
  // (see TerminalGrid.tsx) has been shown once — persisted so it never
  // nags again after the first terminal pane is opened, this session or
  // any future one.
  hasSeenTerminalAccessNotice: boolean;
}

interface UiSettingsStore extends UiSettings {
  setBackendHttpUrl: (url: string) => void;
  setDefaultDepartment: (dept: string) => void;
  setReduceMotion: (on: boolean) => void;
  setTheme: (theme: "hawaii" | "terminal") => void;
  setDesktopNotificationsEnabled: (on: boolean) => void;
  setDesktopHotkey: (shortcut: string) => void;
  markTerminalAccessNoticeSeen: () => void;
  reset: () => void;
}

export const DEFAULT_UI_SETTINGS: UiSettings = {
  backendHttpUrl: "http://localhost:8010",
  defaultDepartment: "Engineering",
  reduceMotion: false,
  theme: "hawaii",
  desktopNotificationsEnabled: true,
  desktopHotkey: "CmdOrCtrl+Shift+H",
  hasSeenTerminalAccessNotice: false,
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
      setDesktopNotificationsEnabled: (desktopNotificationsEnabled) => set({ desktopNotificationsEnabled }),
      setDesktopHotkey: (desktopHotkey) => set({ desktopHotkey: desktopHotkey.trim() || DEFAULT_UI_SETTINGS.desktopHotkey }),
      markTerminalAccessNoticeSeen: () => set({ hasSeenTerminalAccessNotice: true }),
      reset: () => set(DEFAULT_UI_SETTINGS),
    }),
    { name: "studio-ops-ui-settings" },
  ),
);
