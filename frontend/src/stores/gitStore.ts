"use client";

import { create } from "zustand";
import { getHttpBase, fetchWithRetry } from "@/systems/backendUrl";

export interface GitRepo {
  path: string;
  name: string;
  valid: boolean;
  branch?: string | null;
  remote?: string | null;
  dirty?: number;
  ahead?: number | null;
  behind?: number | null;
  hasUpstream?: boolean;
  lastCommit?: string | null;
}

export interface PushResult {
  ok: boolean;
  step?: string | null;
  committed?: boolean;
  branch?: string | null;
  output: string;
}

export interface GithubStatus {
  connected: boolean;
  login?: string;
  avatar?: string;
  reason?: string;
}

export interface GithubRepo {
  fullName: string;
  cloneUrl: string;
  private: boolean;
  pushedAt: string | null;
}

interface GitStore {
  active: string | null;
  repos: GitRepo[];
  loading: boolean;
  pushing: boolean;
  lastPush: PushResult | null;
  error: string | null;
  github: GithubStatus | null;
  githubRepos: GithubRepo[];
  githubLoading: boolean;
  connecting: boolean;
  selecting: string | null; // fullName currently being cloned/selected
  refresh: () => Promise<void>;
  addRepo: (path: string) => Promise<boolean>;
  setActive: (path: string) => Promise<void>;
  removeRepo: (path: string) => Promise<void>;
  push: (message?: string) => Promise<void>;
  clearPushResult: () => void;
  fetchGithub: () => Promise<void>;
  connectGithub: (token: string) => Promise<boolean>;
  selectGithub: (repo: GithubRepo) => Promise<void>;
}

function applyState(set: (p: Partial<GitStore>) => void, data: { active: string | null; repos: GitRepo[] }) {
  set({ active: data.active, repos: data.repos ?? [] });
}

export const useGitStore = create<GitStore>()((set, get) => ({
  active: null,
  repos: [],
  loading: false,
  pushing: false,
  lastPush: null,
  error: null,
  github: null,
  githubRepos: [],
  githubLoading: false,
  connecting: false,
  selecting: null,

  refresh: async () => {
    set({ loading: true, error: null });
    try {
      const resp = await fetchWithRetry(`${getHttpBase()}/api/v1/git`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      applyState(set, await resp.json());
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      set({ loading: false });
    }
  },

  addRepo: async (path) => {
    set({ error: null });
    try {
      const resp = await fetch(`${getHttpBase()}/api/v1/git/repos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${resp.status}`);
      }
      applyState(set, await resp.json());
      return true;
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
      return false;
    }
  },

  setActive: async (path) => {
    const resp = await fetch(`${getHttpBase()}/api/v1/git/active`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    if (resp.ok) applyState(set, await resp.json());
  },

  removeRepo: async (path) => {
    const resp = await fetch(`${getHttpBase()}/api/v1/git/repos?path=${encodeURIComponent(path)}`, {
      method: "DELETE",
    });
    if (resp.ok) applyState(set, await resp.json());
  },

  push: async (message) => {
    set({ pushing: true, lastPush: null, error: null });
    try {
      const resp = await fetch(`${getHttpBase()}/api/v1/git/push`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message || undefined }),
      });
      const result: PushResult = await resp.json();
      set({ lastPush: result });
      // Refresh so ahead/behind/dirty reflect the push outcome.
      await get().refresh();
    } catch (e) {
      set({ lastPush: { ok: false, output: e instanceof Error ? e.message : String(e) } });
    } finally {
      set({ pushing: false });
    }
  },

  clearPushResult: () => set({ lastPush: null }),

  fetchGithub: async () => {
    set({ githubLoading: true });
    try {
      const resp = await fetchWithRetry(`${getHttpBase()}/api/v1/git/github`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      set({ github: data.status ?? null, githubRepos: data.repos ?? [] });
    } catch (e) {
      set({ github: { connected: false, reason: e instanceof Error ? e.message : String(e) } });
    } finally {
      set({ githubLoading: false });
    }
  },

  connectGithub: async (token) => {
    set({ connecting: true, error: null });
    try {
      const resp = await fetch(`${getHttpBase()}/api/v1/git/github/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const status: GithubStatus = await resp.json();
      set({ github: status });
      if (status.connected) {
        await get().fetchGithub();
        return true;
      }
      set({ error: status.reason ?? "could not connect" });
      return false;
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
      return false;
    } finally {
      set({ connecting: false });
    }
  },

  selectGithub: async (repo) => {
    set({ selecting: repo.fullName, error: null });
    try {
      const resp = await fetch(`${getHttpBase()}/api/v1/git/github/select`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: repo.fullName, clone_url: repo.cloneUrl }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${resp.status}`);
      }
      applyState(set, await resp.json());
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      set({ selecting: null });
    }
  },
}));
