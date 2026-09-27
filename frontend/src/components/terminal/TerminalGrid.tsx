"use client";

import { useRef, useState } from "react";
import type { ReactNode } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { TerminalPane } from "./TerminalPane";
import { useTerminalStore, selectPanesFor, type TerminalKind } from "@/stores/terminalStore";
import { useUiSettingsStore } from "@/stores/uiSettingsStore";
import { useFocusTrap } from "@/systems/useFocusTrap";

const KINDS: { value: TerminalKind; label: string }[] = [
  { value: "shell", label: "shell" },
  { value: "claude", label: "claude" },
  { value: "codex", label: "codex" },
  { value: "antigravity", label: "antigravity" },
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
  const hasSeenAccessNotice = useUiSettingsStore((s) => s.hasSeenTerminalAccessNotice);
  const markAccessNoticeSeen = useUiSettingsStore((s) => s.markTerminalAccessNoticeSeen);
  const [pendingNotice, setPendingNotice] = useState(false);
  const addButtonRef = useRef<HTMLButtonElement>(null);

  const actuallyCreate = async () => {
    setCreating(true);
    await create(workspaceId, cwd, newKind);
    setCreating(false);
  };

  const handleAdd = async () => {
    // First-ever terminal pane on macOS triggers the OS's own "give this
    // app access to your files/folders" prompt the moment the PTY tries to
    // read the workspace's cwd — surprising and unexplained if it just
    // appears. Explain it once, then remember (see uiSettingsStore).
    if (!hasSeenAccessNotice) {
      setPendingNotice(true);
      return;
    }
    await actuallyCreate();
  };

  const confirmNotice = async () => {
    markAccessNoticeSeen();
    setPendingNotice(false);
    await actuallyCreate();
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
        <button ref={addButtonRef} onClick={() => void handleAdd()} disabled={creating}>
          {creating ? "opening…" : "+ pane"}
        </button>
        {error && <span className="terminal-grid-error">{error}</span>}
      </div>
      {pendingNotice && (
        <TerminalAccessNotice
          onCancel={() => setPendingNotice(false)}
          onConfirm={() => void confirmNotice()}
        />
      )}
      {panes.length === 0 ? (
        <div className="panel-empty">
          <span className="panel-empty-icon" aria-hidden="true">▢</span>
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

// Shown exactly once, ever (see uiSettingsStore's hasSeenTerminalAccessNotice),
// right before the very first terminal pane is opened: on macOS, the PTY
// backing that pane reads/writes files under the workspace's folder the
// moment it starts, which is exactly when macOS's own "<App> would like to
// access files in <folder>" system dialog appears — unexplained, that looks
// like an unrelated interruption. This just names it ahead of time.
function TerminalAccessNotice({
  onCancel,
  onConfirm,
}: {
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const dialogRef = useFocusTrap<HTMLDivElement>(onCancel);
  return (
    <div className="add-agent-overlay">
      <div
        ref={dialogRef}
        className="add-agent-modal pixel-frame terminal-access-notice"
        role="dialog"
        aria-modal="true"
        aria-label="macOS file access notice"
        tabIndex={-1}
      >
        <div className="add-agent-header">
          <span>heads up: a macOS permission dialog is coming</span>
        </div>
        <p>
          Opening a terminal pane starts a real shell in this workspace's folder. macOS is about
          to show its own system dialog asking whether this app can access files there — that's
          normal, it's macOS (not this app) protecting your files, and it only asks once per
          folder.
        </p>
        <p>Click <strong>Allow</strong> on that system dialog so the terminal can read/write the workspace.</p>
        <div className="add-agent-actions">
          <button onClick={onCancel} className="git-bar-btn-ghost git-bar-btn">
            cancel
          </button>
          <button className="add-agent-submit" onClick={onConfirm}>
            got it, continue
          </button>
        </div>
      </div>
    </div>
  );
}
