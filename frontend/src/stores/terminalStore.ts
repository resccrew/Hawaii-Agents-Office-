"use client";

import { create } from "zustand";
import { getHttpBase } from "@/systems/backendUrl";

export type TerminalKind = "shell" | "claude" | "codex";
export type TerminalStatus = "running" | "exited";

export interface TerminalPane {
  id: string;
  workspaceId: string;
  kind: TerminalKind;
  status: TerminalStatus;
  createdAt: string;
}

interface TerminalStore {
  panesByWorkspace: Map<string, TerminalPane[]>;
  error: string | null;
  refresh: (workspaceId: string) => Promise<void>;
  create: (workspaceId: string, cwd: string, kind?: TerminalKind) => Promise<TerminalPane | null>;
  close: (paneId: string, workspaceId: string) => Promise<void>;
}

export const useTerminalStore = create<TerminalStore>()((set, get) => ({
  panesByWorkspace: new Map(),
  error: null,

  refresh: async (workspaceId) => {
    try {
      const resp = await fetch(`${getHttpBase()}/api/v1/terminal?workspace_id=${encodeURIComponent(workspaceId)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const panes: TerminalPane[] = await resp.json();
      set((s) => {
        const next = new Map(s.panesByWorkspace);
        next.set(workspaceId, panes);
        return { panesByWorkspace: next };
      });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },

  create: async (workspaceId, cwd, kind = "shell") => {
    set({ error: null });
    try {
      const resp = await fetch(`${getHttpBase()}/api/v1/terminal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId, cwd, kind }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${resp.status}`);
      }
      const pane: TerminalPane = await resp.json();
      set((s) => {
        const next = new Map(s.panesByWorkspace);
        next.set(workspaceId, [...(next.get(workspaceId) ?? []), pane]);
        return { panesByWorkspace: next };
      });
      return pane;
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
      return null;
    }
  },

  close: async (paneId, workspaceId) => {
    try {
      await fetch(`${getHttpBase()}/api/v1/terminal/${paneId}`, { method: "DELETE" });
    } finally {
      set((s) => {
        const next = new Map(s.panesByWorkspace);
        next.set(workspaceId, (next.get(workspaceId) ?? []).filter((p) => p.id !== paneId));
        return { panesByWorkspace: next };
      });
      void get().refresh(workspaceId);
    }
  },
}));

const EMPTY_PANES: TerminalPane[] = [];
export const selectPanesFor = (workspaceId: string) => (s: TerminalStore) =>
  s.panesByWorkspace.get(workspaceId) ?? EMPTY_PANES;
