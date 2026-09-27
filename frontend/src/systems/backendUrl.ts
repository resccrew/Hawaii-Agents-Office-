"use client";

import { useUiSettingsStore } from "@/stores/uiSettingsStore";
import { getApiToken } from "./apiAuth";

// Single source of truth for "where is the backend" — reads the
// General-settings override (see SettingsModal's "general" tab) at CALL
// time, so every REST/WS call site picks up a saved change immediately
// without a rebuild. Previously "http://localhost:8010" was hardcoded as a
// default parameter value in ~9 separate places across the app; now they
// all call these two functions instead.
export function getHttpBase(): string {
  return useUiSettingsStore.getState().backendHttpUrl;
}

export function getWsBase(): string {
  return getHttpBase().replace(/^http/, "ws");
}

// The packaged desktop app spawns its backend as a sidecar process that
// takes up to ~15s to bind its port (PyInstaller onefile self-extraction
// runs on every launch), while the frontend's mount-time fetches fire as
// soon as the page paints — racing it and landing a permanent "Load failed"
// since those calls only ever run once. Retry for up to ~40s before giving
// up; use this in place of a bare fetch() for anything called once on
// mount (not for user-triggered actions after the app is already up).
export async function fetchWithRetry(url: string, attempts = 40, delayMs = 1000): Promise<Response> {
  let lastError: unknown;
  const token = await getApiToken();
  const headers: HeadersInit | undefined = token ? { "X-API-Key": token } : undefined;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fetch(url, { headers });
    } catch (e) {
      lastError = e;
      if (i < attempts - 1) await new Promise((r) => setTimeout(r, delayMs));
    }
  }
  throw lastError;
}
