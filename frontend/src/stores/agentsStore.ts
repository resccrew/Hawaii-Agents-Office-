"use client";

import { create } from "zustand";
import { getAgents, deleteAgent, type AgentSummary } from "@/systems/api";

// One shared poll of GET /api/v1/agents feeding every consumer (toolbar
// status chip, sidebar roster) instead of each component running its own
// interval. Doubles as the backend liveness probe: a failed poll flips
// `online` to false, which the toolbar surfaces as the offline dot — the
// "Failed to fetch with zero explanation" problem from the spawn modal.
interface AgentsStore {
  agents: AgentSummary[];
  online: boolean | null; // null = first load still in flight
  stopping: string | null;
  error: string | null;
  refresh: () => Promise<void>;
  stop: (agentId: string) => Promise<void>;
}

export const useAgentsStore = create<AgentsStore>()((set, get) => ({
  agents: [],
  online: null,
  stopping: null,
  error: null,

  refresh: async () => {
    try {
      const agents = await getAgents();
      set({ agents, online: true, error: null });
    } catch {
      set({ online: false });
    }
  },

  stop: async (agentId) => {
    set({ stopping: agentId, error: null });
    try {
      await deleteAgent(agentId);
      set({ agents: get().agents.filter((a) => a.agentId !== agentId) });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) });
    } finally {
      set({ stopping: null });
    }
  },
}));

const POLL_MS = 4000;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let pollUsers = 0;

/** Ref-counted singleton poll — call from a mount effect, invoke the
 * returned cleanup on unmount. Multiple mounted consumers share one timer. */
export function startAgentsPolling(): () => void {
  pollUsers += 1;
  if (!pollTimer) {
    void useAgentsStore.getState().refresh();
    pollTimer = setInterval(() => void useAgentsStore.getState().refresh(), POLL_MS);
  }
  return () => {
    pollUsers -= 1;
    if (pollUsers <= 0 && pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  };
}

export const selectAgents = (s: AgentsStore) => s.agents;
export const selectOnline = (s: AgentsStore) => s.online;
