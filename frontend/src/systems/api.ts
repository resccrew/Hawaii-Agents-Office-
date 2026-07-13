"use client";

import { getHttpBase } from "./backendUrl";

// Shared REST helper. Was previously duplicated as a raw `fetch` +
// `apiBase = "http://localhost:8010"` default param in AddAgentButton.tsx and
// taskStore.ts — new call sites (agent list/stop) go through here instead of
// adding a 4th copy. Backend base URL comes from getHttpBase() (General
// settings override, see uiSettingsStore.ts) so every call site here picks
// up a saved change immediately.

export interface AgentSummary {
  agentId: string;
  provider: string;
  departmentId: string;
  role: string;
  name: string;
  status: "starting" | "active" | "error";
  sessionId: string | null;
  lastError: string | null;
}

export async function getAgents(apiBase = getHttpBase()): Promise<AgentSummary[]> {
  const resp = await fetch(`${apiBase}/api/v1/agents`);
  if (!resp.ok) throw new Error(`GET /agents failed: HTTP ${resp.status}`);
  return resp.json();
}

export async function deleteAgent(agentId: string, apiBase = getHttpBase()): Promise<void> {
  const resp = await fetch(`${apiBase}/api/v1/agents/${agentId}`, { method: "DELETE" });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail ?? `DELETE /agents/${agentId} failed: HTTP ${resp.status}`);
  }
}

export interface SettingField {
  key: string;
  label: string;
  kind: "secret" | "text";
  configured: boolean;
  source: "override" | "env" | "unset";
  preview: string | null;
}

export async function getSettings(apiBase = getHttpBase()): Promise<SettingField[]> {
  const resp = await fetch(`${apiBase}/api/v1/settings`);
  if (!resp.ok) throw new Error(`GET /settings failed: HTTP ${resp.status}`);
  return resp.json();
}

export async function updateSettings(
  values: Record<string, string>,
  apiBase = getHttpBase(),
): Promise<SettingField[]> {
  const resp = await fetch(`${apiBase}/api/v1/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail ?? `PUT /settings failed: HTTP ${resp.status}`);
  }
  return resp.json();
}

export interface ModelCatalog {
  models: string[];
  source: "live" | "fallback" | "unreachable";
}

export async function getModelCatalog(
  provider: string,
  apiBase = getHttpBase(),
): Promise<ModelCatalog> {
  const resp = await fetch(`${apiBase}/api/v1/settings/models/${provider}`);
  if (!resp.ok) throw new Error(`GET /settings/models/${provider} failed: HTTP ${resp.status}`);
  return resp.json();
}
