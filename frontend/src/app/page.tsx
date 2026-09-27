"use client";

import { useEffect, useRef, useState } from "react";
import { ChatLayer } from "@/components/chat/ChatLayer";
import { SidePanel } from "@/components/panels/SidePanel";
import { ActivityLog } from "@/components/panels/ActivityLog";
import { GitBar } from "@/components/panels/GitBar";
import { SettingsModal } from "@/components/panels/SettingsModal";
import { AddAgentButton } from "@/components/agents/AddAgentButton";
import { WorkspaceTabs } from "@/components/panels/WorkspaceTabs";
import { TaskBoard } from "@/components/tasks/TaskBoard";
import { TerminalGrid } from "@/components/terminal/TerminalGrid";
import { selectDepartmentId, useGameStore } from "@/stores/gameStore";
import { useChatStore } from "@/stores/chatStore";
import { useRoomStore, selectRoomSessions } from "@/stores/roomStore";
import { useAgentsStore, selectAgents, selectOnline } from "@/stores/agentsStore";
import { useUiSettingsStore } from "@/stores/uiSettingsStore";
import { useWorkspaceStore, selectActiveWorkspace } from "@/stores/workspaceStore";
import { useTerminalStore } from "@/stores/terminalStore";
import { connectOverview } from "@/systems/roomSocketController";
import { startDesktopBridge } from "@/systems/desktopBridge";

// Layout (Phase 2 of the BridgeSpace rework): the workspace tab strip +
// active workspace's kanban board is now the primary screen — the
// pixel-art office is a small decorative corner dock (still the same
// RoomGame/pixi.js canvas, driven by the same studio-wide /ws/overview
// feed, just no longer claiming the main content area). Chat still opens
// as a draggable popup anchored to wherever the clicked sprite is inside
// that dock.
export default function Home() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const departmentId = useGameStore(selectDepartmentId);
  const activeWorkspace = useWorkspaceStore(selectActiveWorkspace);
  // The kanban board (main content) follows the human's explicitly chosen
  // workspace tab; the office dock keeps following whichever session the
  // server happens to be observing (gameStore's own department) — these
  // are deliberately independent now that the dock is decoration, not the
  // primary navigation surface.
  const boardDepartmentId = activeWorkspace?.departmentId ?? departmentId ?? "Engineering";
  const [mainView, setMainView] = useState<"board" | "terminal">("board");
  const [leftPanelOpen, setLeftPanelOpen] = useState(true);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const refreshPanes = useTerminalStore((s) => s.refresh);
  const openChatPanel = useChatStore((s) => s.openPanel);
  const roomSessions = useRoomStore(selectRoomSessions);
  const agents = useAgentsStore(selectAgents);
  const online = useAgentsStore(selectOnline);
  const refreshAgents = useAgentsStore((s) => s.refresh);
  const roomDisconnectRef = useRef<() => void>(() => {});
  const reduceMotion = useUiSettingsStore((s) => s.reduceMotion);
  const theme = useUiSettingsStore((s) => s.theme);

  useEffect(() => {
    roomDisconnectRef.current = connectOverview();
    return () => roomDisconnectRef.current();
  }, []);

  // Notifications/dock badge/tray/hotkey (see systems/desktopBridge.ts) —
  // reads the same roomStore this same effect's connectOverview() feeds,
  // no separate WS connection. No-ops in a plain browser dev session.
  useEffect(() => startDesktopBridge(), []);

  // Bugfix: panes are keyed by workspace id in the store, but nothing was
  // re-fetching them when the active workspace changed while already on
  // the terminal view — switching tabs showed the PREVIOUS workspace's
  // (or an empty) pane list until some other action happened to trigger a
  // refresh. Keep it in sync with whichever workspace is actually active.
  const activeWorkspaceId = activeWorkspace?.id ?? null;
  useEffect(() => {
    if (activeWorkspaceId) void refreshPanes(activeWorkspaceId);
  }, [activeWorkspaceId, refreshPanes]);

  // General settings → "reduce motion" and "theme" — stamped on <html> so the CSS
  // attribute-selector twin of the OS prefers-reduced-motion query (see
  // globals.css) can apply regardless of the OS-level setting.
  useEffect(() => {
    document.documentElement.dataset.reduceMotion = String(reduceMotion);
    document.documentElement.dataset.theme = theme;
  }, [reduceMotion, theme]);

  const handleAgentSpawned = (newSessionId: string) => {
    // The new agent appears immediately — it's already in the shared room,
    // just open its chat and nudge the roster poll so it shows up at once.
    void refreshAgents();
    openChatPanel(newSessionId);
  };

  // "Select this agent" always means "open its chat", whether the click
  // came from the sprite in the office or a roster card in the side panel.
  const handleSelectAgent = (targetSessionId: string) => {
    openChatPanel(targetSessionId);
  };

  // (Removed anchorFor logic since ChatLayer is now full-screen and unanchored)

  return (
    <main>
      <div className="toolbar">
        <span className="toolbar-title">
          <span className="toolbar-logo" aria-hidden="true">🌴</span>
          <span className="toolbar-wordmark">Hawaii Agents Office</span>
        </span>
        <GitBar />
        <div className="toolbar-spacer" />
        <AddAgentButton onSpawned={handleAgentSpawned} />
        <button className="pixel-frame" onClick={() => setLeftPanelOpen(!leftPanelOpen)}>
          {leftPanelOpen ? "hide log" : "show log"}
        </button>
        <button className="pixel-frame" onClick={() => setRightPanelOpen(!rightPanelOpen)}>
          {rightPanelOpen ? "hide team" : "show team"}
        </button>
        <button className="pixel-frame" onClick={() => setSettingsOpen(true)}>
          settings
        </button>
        <div className="toolbar-spacer" />
        <span className="toolbar-chip">
          <span className={`status-dot status-dot-${online === null ? "starting" : online ? "active" : "error"}`} />
          {online === null ? "connecting…" : online ? "online" : "backend offline"}
        </span>
        <span className="toolbar-chip">◉ {agents.length} agent{agents.length === 1 ? "" : "s"}</span>
      </div>
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
      
      {leftPanelOpen && (
        <aside className="side-panel-left">
          <ActivityLog />
        </aside>
      )}

      <div 
        className="main-content"
        style={{
          left: leftPanelOpen ? "var(--panel-w-left)" : "0px",
          right: rightPanelOpen ? "var(--panel-w)" : "0px"
        }}
      >
        <div className="main-header">
          <WorkspaceTabs />
          <div className="main-view-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={mainView === "board"}
              className={mainView === "board" ? "main-view-tab main-view-tab-active" : "main-view-tab"}
              onClick={() => setMainView("board")}
            >
              board
            </button>
            <button
              role="tab"
              aria-selected={mainView === "terminal"}
              className={mainView === "terminal" ? "main-view-tab main-view-tab-active" : "main-view-tab"}
              onClick={() => setMainView("terminal")}
            >
              terminal
            </button>
          </div>
        </div>
        <div style={{ position: "relative", flex: 1, minHeight: 0 }}>
          <div style={{
            position: "absolute", inset: 0,
            display: "flex", flexDirection: "column",
            visibility: mainView === "board" ? "visible" : "hidden",
            pointerEvents: mainView === "board" ? "auto" : "none",
            opacity: mainView === "board" ? 1 : 0
          }}>
            <TaskBoard departmentId={boardDepartmentId} />
          </div>
          <div style={{
            position: "absolute", inset: 0,
            display: "flex", flexDirection: "column",
            visibility: mainView === "terminal" ? "visible" : "hidden",
            pointerEvents: mainView === "terminal" ? "auto" : "none",
            opacity: mainView === "terminal" ? 1 : 0
          }}>
            {activeWorkspace ? (
              <TerminalGrid
                workspaceId={activeWorkspace.id}
                workspaceName={activeWorkspace.name}
                cwd={activeWorkspace.repoPath}
              />
            ) : (
              <div className="panel-empty">no workspace selected</div>
            )}
          </div>
        </div>
      </div>
      <ChatLayer />
      {rightPanelOpen && (
        <SidePanel departmentId={boardDepartmentId} onSelectAgent={handleSelectAgent} />
      )}
    </main>
  );
}
