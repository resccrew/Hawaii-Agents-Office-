"use client";

import { useEffect, useState } from "react";
import {
  useWorkspaceStore,
  selectWorkspaces,
  selectActiveWorkspace,
} from "@/stores/workspaceStore";

// The project tab strip — each tab is a Workspace (a repo checkout + the
// department that owns its agents/kanban). Switching tabs flips both the
// active workspace AND git_ops's own active repo (see workspaceStore.activate),
// so GitBar reflects whichever tab is selected without needing its own
// workspace-awareness.
export function WorkspaceTabs() {
  const workspaces = useWorkspaceStore(selectWorkspaces);
  const active = useWorkspaceStore(selectActiveWorkspace);
  const activeId = useWorkspaceStore((s) => s.activeId);
  const error = useWorkspaceStore((s) => s.error);
  const refresh = useWorkspaceStore((s) => s.refresh);
  const activate = useWorkspaceStore((s) => s.activate);
  const create = useWorkspaceStore((s) => s.create);
  const remove = useWorkspaceStore((s) => s.remove);

  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleCreate = async () => {
    if (!name.trim() || !repoPath.trim()) return;
    setSubmitting(true);
    const ok = await create(name.trim(), repoPath.trim());
    setSubmitting(false);
    if (ok) {
      setName("");
      setRepoPath("");
      setAdding(false);
    }
  };

  return (
    <div className="workspace-tabs">
      <div className="workspace-tabs-list">
        {workspaces.map((w) => (
          <div
            key={w.id}
            className={`workspace-tab${w.id === activeId ? " workspace-tab-active" : ""}`}
            onClick={() => w.id !== activeId && void activate(w.id)}
            role="tab"
            aria-selected={w.id === activeId}
            title={w.repoPath}
          >
            <span className="workspace-tab-name">{w.name}</span>
            {workspaces.length > 1 && (
              <button
                className="workspace-tab-close"
                aria-label={`remove workspace ${w.name}`}
                onClick={(e) => {
                  e.stopPropagation();
                  void remove(w.id);
                }}
              >
                ✕
              </button>
            )}
          </div>
        ))}
        {!adding && (
          <button className="workspace-tab-add" onClick={() => setAdding(true)} title="add workspace">
            +
          </button>
        )}
        {adding && (
          <div className="workspace-tab-form">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="name"
              autoFocus
            />
            <input
              value={repoPath}
              onChange={(e) => setRepoPath(e.target.value)}
              placeholder="/path/to/repo"
              onKeyDown={(e) => e.key === "Enter" && void handleCreate()}
            />
            <button onClick={() => void handleCreate()} disabled={submitting}>
              {submitting ? "…" : "add"}
            </button>
            <button
              className="workspace-tab-form-cancel"
              onClick={() => {
                setAdding(false);
                setName("");
                setRepoPath("");
              }}
            >
              ✕
            </button>
          </div>
        )}
      </div>
      {error && <span className="workspace-tabs-error">{error}</span>}
      {active && <span className="workspace-tabs-path">{active.repoPath}</span>}
    </div>
  );
}
