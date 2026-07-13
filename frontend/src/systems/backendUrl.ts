"use client";

import { useUiSettingsStore } from "@/stores/uiSettingsStore";

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
