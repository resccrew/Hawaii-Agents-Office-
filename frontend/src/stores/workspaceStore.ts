"use client";

import { create } from "zustand";
import { getHttpBase } from "@/systems/backendUrl";

export interface Workspace {
  id: string;
  name: string;
  repoPath: string;
  departmentId: string;
  createdAt: string;
}

interface WorkspaceStore {
  workspaces: Workspace[];
  activeId: string | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  create: (name: string, repoPath: string) => Promise<boolean>;
  activate: (id: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
}

export const useWorkspaceStore = create<WorkspaceStore>()((set, get) => ({
  workspaces: [],
  activeId: null,
  loading: false,
  error: null,

  refresh: async () => {
    set({ loading: true, error: null });
    try {
      const resp = await fetch(`${getHttpBase()}/api/v1/workspaces`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      set({ workspaces: data.workspaces ?? [], activeId: data.activeId ?? null });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      set({ loading: false });
    }
  },

  create: async (name, repoPath) => {
    set({ error: null });
    try {
      const resp = await fetch(`${getHttpBase()}/api/v1/workspaces`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, repo_path: repoPath }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${resp.status}`);
      }
      await get().refresh();
      return true;
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
      return false;
    }
  },

  activate: async (id) => {
    // Optimistic — switching tabs should feel instant; refresh() below
    // reconciles with the server (and with git_ops's own active-repo flip)
    // right after.
    set({ activeId: id });
    try {
      const resp = await fetch(`${getHttpBase()}/api/v1/workspaces/${id}/activate`, { method: "POST" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      await get().refresh();
    }
  },

  remove: async (id) => {
    try {
      const resp = await fetch(`${getHttpBase()}/api/v1/workspaces/${id}`, { method: "DELETE" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      await get().refresh();
    }
  },
}));

export const selectWorkspaces = (s: WorkspaceStore) => s.workspaces;
export const selectActiveWorkspace = (s: WorkspaceStore) =>
  s.workspaces.find((w) => w.id === s.activeId) ?? null;
