"use client";

import { useEffect, useRef, useState } from "react";
import { RoomGame } from "@/components/game/RoomGame";
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
import { CEO_SPOT } from "@/systems/layout";
import { lastTargetOf } from "@/systems/officeMovement";
import { STAGE_WIDTH, STAGE_HEIGHT } from "@/components/game/StudioGame";
import { connectOverview } from "@/systems/roomSocketController";
import { useFitSize } from "@/systems/useFitSize";

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
  const refreshPanes = useTerminalStore((s) => s.refresh);
  const openChatPanel = useChatStore((s) => s.openPanel);
  const roomSessions = useRoomStore(selectRoomSessions);
  const agents = useAgentsStore(selectAgents);
  const online = useAgentsStore(selectOnline);
  const refreshAgents = useAgentsStore((s) => s.refresh);
  const roomDisconnectRef = useRef<() => void>(() => {});
  const stageWrapperRef = useRef<HTMLDivElement>(null);
  const stageSize = useFitSize(stageWrapperRef);
  const reduceMotion = useUiSettingsStore((s) => s.reduceMotion);

  useEffect(() => {
    roomDisconnectRef.current = connectOverview();
    return () => roomDisconnectRef.current();
  }, []);

  // Bugfix: panes are keyed by workspace id in the store, but nothing was
  // re-fetching them when the active workspace changed while already on
  // the terminal view — switching tabs showed the PREVIOUS workspace's
  // (or an empty) pane list until some other action happened to trigger a
  // refresh. Keep it in sync with whichever workspace is actually active.
  const activeWorkspaceId = activeWorkspace?.id ?? null;
  useEffect(() => {
    if (activeWorkspaceId) void refreshPanes(activeWorkspaceId);
  }, [activeWorkspaceId, refreshPanes]);

  // General settings → "reduce motion" — stamped on <html> so the CSS
  // attribute-selector twin of the OS prefers-reduced-motion query (see
  // globals.css) can apply regardless of the OS-level setting.
  useEffect(() => {
    document.documentElement.dataset.reduceMotion = String(reduceMotion);
  }, [reduceMotion]);

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

  // Map an agent's CURRENT office position (it walks between the lounge,
  // the CEO, and its desk — see officeMovement.ts) to a pixel position
  // inside the rendered canvas frame, so a chat window opens anchored above
  // wherever the sprite actually is. lastTargetOf returns null before the
  // agent's first plan has been computed (RoomGame hasn't rendered it yet,
  // e.g. it's past the desk-count ceiling) — anchor stays null → the
  // window opens at a default spot instead.
  const anchorFor = (sessionId: string) => {
    if (stageSize.width === 0) return null;
    const target = lastTargetOf(sessionId) ?? (roomSessions.has(sessionId) ? CEO_SPOT : null);
    if (!target) return null;
    return {
      x: (target.x / STAGE_WIDTH) * stageSize.width,
      y: (target.y / STAGE_HEIGHT) * stageSize.height,
    };
  };

  return (
    <main>
      <div className="toolbar">
        <span className="toolbar-title">
          <span className="toolbar-logo" aria-hidden="true">🌴</span>
          <span className="toolbar-wordmark">Hawaii Agents Office</span>
        </span>
        <AddAgentButton onSpawned={handleAgentSpawned} />
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
      <aside className="side-panel-left">
        <ActivityLog />
      </aside>
      <div className="main-content">
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
        {mainView === "board" && <TaskBoard departmentId={boardDepartmentId} />}
        {mainView === "terminal" &&
          (activeWorkspace ? (
            <TerminalGrid
              workspaceId={activeWorkspace.id}
              workspaceName={activeWorkspace.name}
              cwd={activeWorkspace.repoPath}
            />
          ) : (
            <div className="panel-empty">no workspace selected</div>
          ))}
      </div>
      <div ref={stageWrapperRef} className="game-stage-wrapper" title="office (decorative)">
        <div
          className="game-canvas-frame"
          style={{ width: stageSize.width, height: stageSize.height }}
        >
          <RoomGame onAgentClick={handleSelectAgent} />
          <ChatLayer anchorFor={anchorFor} frame={stageSize} />
        </div>
      </div>
      <GitBar />
      <SidePanel departmentId={boardDepartmentId} onSelectAgent={handleSelectAgent} />
    </main>
  );
}
