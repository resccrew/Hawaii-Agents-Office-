"use client";

import { useEffect, useRef, useState } from "react";
import { RoomGame } from "@/components/game/RoomGame";
import { ChatLayer } from "@/components/chat/ChatLayer";
import { SidePanel } from "@/components/panels/SidePanel";
import { ActivityLog } from "@/components/panels/ActivityLog";
import { SettingsModal } from "@/components/panels/SettingsModal";
import { AddAgentButton } from "@/components/agents/AddAgentButton";
import { selectDepartmentId, useGameStore } from "@/stores/gameStore";
import { useChatStore } from "@/stores/chatStore";
import { useRoomStore, selectRoomSessions } from "@/stores/roomStore";
import { useAgentsStore, selectAgents, selectOnline } from "@/stores/agentsStore";
import { useUiSettingsStore } from "@/stores/uiSettingsStore";
import { CEO_SPOT } from "@/systems/layout";
import { lastTargetOf } from "@/systems/officeMovement";
import { STAGE_WIDTH, STAGE_HEIGHT } from "@/components/game/StudioGame";
import { connectOverview } from "@/systems/roomSocketController";
import { useFitSize } from "@/systems/useFitSize";

// Layout: full-bleed office canvas on the left (cover-fit — no letterbox
// bands), docked control panel (team roster + task board) on the right,
// chat as a draggable popup floating over the clicked agent. Everyone
// shares one room via the studio-wide /ws/overview feed.
export default function Home() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const departmentId = useGameStore(selectDepartmentId);
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
      <div ref={stageWrapperRef} className="game-stage-wrapper">
        <div
          className="game-canvas-frame"
          style={{ width: stageSize.width, height: stageSize.height }}
        >
          <RoomGame onAgentClick={handleSelectAgent} />
          <ChatLayer anchorFor={anchorFor} frame={stageSize} />
        </div>
      </div>
      <SidePanel departmentId={departmentId ?? "Engineering"} onSelectAgent={handleSelectAgent} />
    </main>
  );
}
