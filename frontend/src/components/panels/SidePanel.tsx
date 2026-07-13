"use client";

import { useEffect, useState } from "react";
import { TaskBoard } from "@/components/tasks/TaskBoard";
import { useAgentsStore, selectAgents, startAgentsPolling } from "@/stores/agentsStore";
import { useTaskStore, selectTasksFor } from "@/stores/taskStore";
import { useChatStore, selectOpenSessions } from "@/stores/chatStore";

interface Props {
  departmentId: string | null;
  onSelectAgent: (sessionId: string) => void;
}

// The docked right-hand control panel: everything you can *do* in Studio
// Ops that isn't clicking a sprite lives here, split into two tabs —
// "team" (the live agent roster: status, open chat, stop) and "tasks"
// (the shared department task board). Replaces both the old fixed
// TaskBoard panel and the modal AgentListPanel.
export function SidePanel({ departmentId, onSelectAgent }: Props) {
  const [tab, setTab] = useState<"team" | "tasks">("team");
  const agents = useAgentsStore(selectAgents);
  const stopping = useAgentsStore((s) => s.stopping);
  const rosterError = useAgentsStore((s) => s.error);
  const stopAgent = useAgentsStore((s) => s.stop);
  const tasks = useTaskStore(selectTasksFor(departmentId ?? ""));
  const openChats = useChatStore(selectOpenSessions);

  useEffect(() => startAgentsPolling(), []);

  const openTasks = tasks.filter((t) => t.status !== "done").length;

  return (
    <aside className="side-panel">
      <div className="side-panel-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "team"}
          className={tab === "team" ? "side-tab side-tab-active" : "side-tab"}
          onClick={() => setTab("team")}
        >
          team{agents.length > 0 && <span className="side-tab-badge">{agents.length}</span>}
        </button>
        <button
          role="tab"
          aria-selected={tab === "tasks"}
          className={tab === "tasks" ? "side-tab side-tab-active" : "side-tab"}
          onClick={() => setTab("tasks")}
        >
          tasks{openTasks > 0 && <span className="side-tab-badge">{openTasks}</span>}
        </button>
      </div>

      {tab === "tasks" && <TaskBoard departmentId={departmentId} />}

      {tab === "team" && (
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
      )}
    </aside>
  );
}
