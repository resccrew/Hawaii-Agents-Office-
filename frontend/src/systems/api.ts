"use client";

import { authedFetch } from "./apiAuth";
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
  const resp = await authedFetch(`${apiBase}/api/v1/agents`);
  if (!resp.ok) throw new Error(`GET /agents failed: HTTP ${resp.status}`);
  return resp.json();
}

export async function deleteAgent(agentId: string, apiBase = getHttpBase()): Promise<void> {
  const resp = await authedFetch(`${apiBase}/api/v1/agents/${agentId}`, { method: "DELETE" });
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
  const resp = await authedFetch(`${apiBase}/api/v1/settings`);
  if (!resp.ok) throw new Error(`GET /settings failed: HTTP ${resp.status}`);
  return resp.json();
}

export async function updateSettings(
  values: Record<string, string>,
  apiBase = getHttpBase(),
): Promise<SettingField[]> {
  const resp = await authedFetch(`${apiBase}/api/v1/settings`, {
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
  const resp = await authedFetch(`${apiBase}/api/v1/settings/models/${provider}`);
  if (!resp.ok) throw new Error(`GET /settings/models/${provider} failed: HTTP ${resp.status}`);
  return resp.json();
}

// Agent + office memory (backend/app/core/memory_store.py + api/routes/memory.py).
// scope is either "office" (shared, project-wide memory) or an agent_id
// (that agent's own memory) — the backend validates it, this layer just
// passes it through.
export interface MemoryIndexEntry {
  slug: string;
  name: string;
  description: string;
}

export interface MemoryFact {
  scope: string;
  slug: string;
  name: string;
  description: string;
  type: "user" | "feedback" | "project" | "reference";
  body: string;
  updatedAt: string;
}

async function memoryErrorFrom(resp: Response, fallback: string): Promise<Error> {
  const body = await resp.json().catch(() => ({}));
  return new Error(body.detail ?? `${fallback}: HTTP ${resp.status}`);
}

export async function listMemory(scope: string, apiBase = getHttpBase()): Promise<MemoryIndexEntry[]> {
  const resp = await authedFetch(`${apiBase}/api/v1/memory/${encodeURIComponent(scope)}`);
  if (!resp.ok) throw await memoryErrorFrom(resp, `GET /memory/${scope} failed`);
  return resp.json();
}

export async function readMemory(scope: string, slug: string, apiBase = getHttpBase()): Promise<MemoryFact> {
  const resp = await authedFetch(`${apiBase}/api/v1/memory/${encodeURIComponent(scope)}/${encodeURIComponent(slug)}`);
  if (!resp.ok) throw await memoryErrorFrom(resp, `GET /memory/${scope}/${slug} failed`);
  return resp.json();
}

export async function writeMemory(
  scope: string,
  slug: string,
  fields: { name: string; description: string; type: string; body: string },
  apiBase = getHttpBase(),
): Promise<MemoryFact> {
  const resp = await authedFetch(`${apiBase}/api/v1/memory/${encodeURIComponent(scope)}/${encodeURIComponent(slug)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (!resp.ok) throw await memoryErrorFrom(resp, `PUT /memory/${scope}/${slug} failed`);
  return resp.json();
}

export async function deleteMemory(scope: string, slug: string, apiBase = getHttpBase()): Promise<void> {
  const resp = await authedFetch(`${apiBase}/api/v1/memory/${encodeURIComponent(scope)}/${encodeURIComponent(slug)}`, {
    method: "DELETE",
  });
  if (!resp.ok) throw await memoryErrorFrom(resp, `DELETE /memory/${scope}/${slug} failed`);
}
