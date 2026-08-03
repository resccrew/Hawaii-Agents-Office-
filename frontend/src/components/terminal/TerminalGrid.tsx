"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { TerminalPane } from "./TerminalPane";
import { useTerminalStore, selectPanesFor, type TerminalKind } from "@/stores/terminalStore";

const KINDS: { value: TerminalKind; label: string }[] = [
  { value: "shell", label: "shell" },
  { value: "claude", label: "claude" },
  { value: "codex", label: "codex" },
];

interface Props {
  workspaceId: string;
  workspaceName: string;
  cwd: string;
}

// Multi-pane terminal grid — the fuller build on top of the Phase 3 spike's
// single hardcoded shell pane. Panes sit side-by-side in one resizable
// horizontal Group (react-resizable-panels v4's `Group`/`Panel`/`Separator`
// — not the `PanelGroup`/`PanelResizeHandle` names from older versions of
// this library). Deliberately flat, not a recursive row-of-columns docking
// layout: N panes in a row covers the "several terminals open at once"
// case without the complexity of an arbitrary split-any-direction system —
// revisit if that turns out to not be enough.
export function TerminalGrid({ workspaceId, workspaceName, cwd }: Props) {
  const panes = useTerminalStore(selectPanesFor(workspaceId));
  const create = useTerminalStore((s) => s.create);
  const close = useTerminalStore((s) => s.close);
  const error = useTerminalStore((s) => s.error);
  const [newKind, setNewKind] = useState<TerminalKind>("shell");
  const [creating, setCreating] = useState(false);

  const handleAdd = async () => {
    setCreating(true);
    await create(workspaceId, cwd, newKind);
    setCreating(false);
  };

  // Panel/Separator must be direct children of Group — build a flat array
  // instead of mapping to a Fragment, so there's no ambiguity about that.
  const groupChildren: ReactNode[] = [];
  panes.forEach((p, i) => {
    if (i > 0) {
      groupChildren.push(<Separator key={`sep-${p.id}`} className="terminal-separator" />);
    }
    groupChildren.push(
      <Panel key={p.id} id={p.id} minSize={15} className="terminal-panel">
        <div className="terminal-pane-toolbar">
          <span>
            {p.kind} — {workspaceName}
            {p.status === "exited" && <span className="terminal-pane-exited"> (exited)</span>}
          </span>
          <button onClick={() => void close(p.id, workspaceId)} title="end this terminal process">
            ✕ close
          </button>
        </div>
        <TerminalPane paneId={p.id} />
      </Panel>,
    );
  });

  return (
    <div className="terminal-grid">
      <div className="terminal-grid-toolbar">
        <select value={newKind} onChange={(e) => setNewKind(e.target.value as TerminalKind)}>
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
        <button onClick={() => void handleAdd()} disabled={creating}>
          {creating ? "opening…" : "+ pane"}
        </button>
        {error && <span className="terminal-grid-error">{error}</span>}
      </div>
      {panes.length === 0 ? (
        <div className="panel-empty">
          <span className="panel-empty-icon">▢</span>
          no terminal panes yet
          <span className="panel-empty-hint">pick a kind above and hit “+ pane”</span>
        </div>
      ) : (
        <Group orientation="horizontal" className="terminal-panel-group">
          {groupChildren}
        </Group>
      )}
    </div>
  );
}
