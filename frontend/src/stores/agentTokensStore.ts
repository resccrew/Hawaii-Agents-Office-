"use client";

import { create } from "zustand";
import { getHttpBase } from "@/systems/backendUrl";
import { authedFetch } from "@/systems/apiAuth";

// Deliberately NOT sharing api.ts's getAgents()/AgentSummary — this reads
// the very same GET /api/v1/agents response but only cares about the
// token/cost fields the backend accumulates per agent (see
// agent_registry.py's AgentSession.input_tokens/... and
// event_processor.py's accumulate_tokens call). Keeping this as its own
// tiny fetch avoids widening the shared AgentSummary type/helper while
// that file is being actively worked on elsewhere.
export interface AgentTokenStats {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
}

interface AgentTokensStore {
  byAgentId: Record<string, AgentTokenStats>;
  refresh: () => Promise<void>;
}

interface RawAgentRow {
  agentId?: string;
  inputTokens?: number;
  outputTokens?: number;
  cacheReadTokens?: number;
  cacheCreationTokens?: number;
}

export const useAgentTokensStore = create<AgentTokensStore>()((set) => ({
  byAgentId: {},
  refresh: async () => {
    try {
      const resp = await authedFetch(`${getHttpBase()}/api/v1/agents`);
      if (!resp.ok) return;
      const rows: RawAgentRow[] = await resp.json();
      const byAgentId: Record<string, AgentTokenStats> = {};
      for (const row of rows) {
        if (!row.agentId) continue;
        byAgentId[row.agentId] = {
          inputTokens: row.inputTokens ?? 0,
          outputTokens: row.outputTokens ?? 0,
          cacheReadTokens: row.cacheReadTokens ?? 0,
          cacheCreationTokens: row.cacheCreationTokens ?? 0,
        };
      }
      set({ byAgentId });
    } catch {
      // Best-effort — the roster's own poll (agentsStore) already surfaces
      // backend-offline; this badge just quietly keeps its last value.
    }
  },
}));

const POLL_MS = 5000;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let pollUsers = 0;

/** Ref-counted singleton poll, same pattern as agentsStore's startAgentsPolling. */
export function startAgentTokensPolling(): () => void {
  pollUsers += 1;
  if (!pollTimer) {
    void useAgentTokensStore.getState().refresh();
    pollTimer = setInterval(() => void useAgentTokensStore.getState().refresh(), POLL_MS);
  }
  return () => {
    pollUsers -= 1;
    if (pollUsers <= 0 && pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  };
}

export const selectAgentTokens = (agentId: string) => (s: AgentTokensStore) =>
  s.byAgentId[agentId];
