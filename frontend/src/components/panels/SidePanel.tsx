"use client";

import { useEffect, useRef } from "react";
import { useAgentsStore, selectAgents, startAgentsPolling } from "@/stores/agentsStore";
import { useChatStore, selectOpenSessions } from "@/stores/chatStore";
import { RoomGame } from "@/components/game/RoomGame";
import { useFitSize } from "@/systems/useFitSize";

interface Props {
  departmentId: string | null;
  onSelectAgent: (sessionId: string) => void;
}

// The docked right-hand control panel: everything you can *do* in Studio
// Ops that isn't clicking a sprite lives here, focused entirely on the
// "team" (the live agent roster: status, open chat, stop).
// The task board has been moved exclusively to the main window.
export function SidePanel({ departmentId, onSelectAgent }: Props) {
  const agents = useAgentsStore(selectAgents);
  const stopping = useAgentsStore((s) => s.stopping);
  const rosterError = useAgentsStore((s) => s.error);
  const stopAgent = useAgentsStore((s) => s.stop);
  const openChats = useChatStore(selectOpenSessions);

  const stageWrapperRef = useRef<HTMLDivElement>(null);
  const stageSize = useFitSize(stageWrapperRef);

  useEffect(() => startAgentsPolling(), []);

  return (
    <aside className="side-panel">
      <div className="side-panel-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={true}
          className="side-tab side-tab-active"
          style={{ cursor: "default" }}
        >
          team{agents.length > 0 && <span className="side-tab-badge">{agents.length}</span>}
        </button>
      </div>

      <div className="team-tab">
        {rosterError && <div className="add-agent-error">error: {rosterError}</div>}
        <div className="team-list">
          {agents.length === 0 && (
            <div className="panel-empty">
              <span className="panel-empty-icon">◉</span>
              office is empty
              <span className="panel-empty-hint">hit “+ agent” to spawn your first teammate</span>
            </div>
          )}
          {agents.map((agent) => {
            const isActiveChat = agent.sessionId !== null && openChats.includes(agent.sessionId);
            return (
              <div
                key={agent.agentId}
                className={`agent-card${isActiveChat ? " agent-card-selected" : ""}${agent.sessionId ? " agent-card-clickable" : ""}`}
                onClick={() => agent.sessionId && onSelectAgent(agent.sessionId)}
              >
                <div className="agent-card-top">
                  <span className={`status-dot status-dot-${agent.status}`} />
                  <span className="agent-card-name">{agent.name}</span>
                  <span className="agent-card-role">{agent.role.replace("_", " ")}</span>
                </div>
                <div className="agent-card-meta">
                  <span>{agent.departmentId}</span>
                  <span className="agent-card-session">{agent.sessionId ? agent.sessionId.slice(0, 8) : "starting…"}</span>
                </div>
                {agent.status === "error" && agent.lastError && (
                  <div className="agent-card-error" title={agent.lastError}>
                    {agent.lastError.slice(0, 80)}
                  </div>
                )}
                <div className="agent-card-actions">
                  <button
                    disabled={!agent.sessionId}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (agent.sessionId) onSelectAgent(agent.sessionId);
                    }}
                  >
                    💬 chat
                  </button>
                  <button
                    className="agent-card-stop"
                    disabled={stopping === agent.agentId}
                    onClick={(e) => {
                      e.stopPropagation();
                      void stopAgent(agent.agentId);
                    }}
                  >
                    {stopping === agent.agentId ? "…" : "■ stop"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      
      <div ref={stageWrapperRef} className="game-stage-wrapper-inline" title="office (decorative)">
        <div
          className="game-canvas-frame"
          style={{ width: stageSize.width, height: stageSize.height }}
        >
          <RoomGame />
        </div>
      </div>
    </aside>
  );
}
