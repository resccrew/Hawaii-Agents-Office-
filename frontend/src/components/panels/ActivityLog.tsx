"use client";

import { useEffect, useRef } from "react";
import { useActivityLogStore, selectLogEntries } from "@/stores/activityLogStore";

// Studio-wide event feed — adapted from claude-office's EventLog panel.
// Every hook event, tool call, and chat turn any agent produces flows
// through here in real time (fed by roomSocketController.ts, which already
// receives each agent's StateMachine.history on every overview broadcast).
// Docked on the LEFT, mirroring the reference's session browser slot —
// makes the office canvas smaller to make room, same as the team/tasks
// panel already does on the right.
const TYPE_CLASS: Record<string, string> = {
  session_start: "log-type-session",
  session_end: "log-type-session",
  pre_tool_use: "log-type-tool",
  post_tool_use: "log-type-tool",
  user_prompt_submit: "log-type-prompt",
  chat_message: "log-type-chat",
  permission_request: "log-type-warn",
  notification: "log-type-warn",
  waiting_permission: "log-type-warn",
  subagent_start: "log-type-agent",
  subagent_stop: "log-type-agent",
  agent_update: "log-type-agent",
  stop: "log-type-idle",
  error: "log-type-error",
  task_created: "log-type-task",
  task_completed: "log-type-task",
};

function typeClass(type: string): string {
  return TYPE_CLASS[type] ?? "log-type-default";
}

function formatType(type: string): string {
  return type.replace(/_/g, " ");
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour12: false });
}

export function ActivityLog() {
  const entries = useActivityLogStore(selectLogEntries);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [entries.length]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  };

  return (
    <div className="activity-log">
      <div className="activity-log-header">
        <span>activity log</span>
        <span className="activity-log-count">{entries.length}</span>
      </div>
      <div className="activity-log-list" ref={scrollRef} onScroll={handleScroll}>
        {entries.length === 0 && (
          <div className="panel-empty">
            <span className="panel-empty-icon" aria-hidden="true">▤</span>
            nothing yet
            <span className="panel-empty-hint">agent activity streams in here live</span>
          </div>
        )}
        {entries.map((e, i) => (
          <div key={`${e.id}-${i}`} className="log-entry">
            <div className="log-entry-top">
              <span className="log-entry-time">{formatTime(e.timestamp)}</span>
              <span className={`log-type-badge ${typeClass(e.type)}`}>{formatType(e.type)}</span>
              {e.agentName && <span className="log-entry-agent">@{e.agentName}</span>}
            </div>
            <div className="log-entry-summary">{e.summary}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
