"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTaskStore, selectTasksFor, connectTaskBoard, createTask, updateTaskStatus } from "@/stores/taskStore";
import type { TaskStatus } from "@/stores/taskStore";

const STATUS_LABEL: Record<TaskStatus, string> = {
  open: "open",
  in_progress: "in progress",
  done: "done",
};

// Turn http(s)/file links inside an agent's result report into clickable
// anchors; everything else (including bare file paths, which browsers block
// from navigating anyway) stays as selectable text.
const LINK_RE = /(https?:\/\/[^\s]+|file:\/\/[^\s]+)/g;
function renderResult(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = new RegExp(LINK_RE);
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(<span key={key++}>{text.slice(last, m.index)}</span>);
    const url = m[0];
    nodes.push(
      <a key={key++} href={url} target="_blank" rel="noreferrer">
        {url}
      </a>,
    );
    last = m.index + url.length;
  }
  if (last < text.length) nodes.push(<span key={key++}>{text.slice(last)}</span>);
  return nodes;
}

// Structured half of Phase 6 coordination — the shared task board every
// agent in a department (and the human) reads/writes to. No longer a
// stand-alone fixed panel: it renders as the "tasks" tab body inside
// SidePanel, which owns the docked frame/positioning.
export function TaskBoard({ departmentId }: { departmentId: string | null }) {
  const tasks = useTaskStore(selectTasksFor(departmentId ?? ""));
  const [draft, setDraft] = useState("");
  // Which done task is expanded to show its result report. Only one at a time.
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const disconnectRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!departmentId) return;
    disconnectRef.current = connectTaskBoard(departmentId);
    return () => disconnectRef.current();
  }, [departmentId]);

  if (!departmentId) return null;

  const handleAdd = () => {
    const subject = draft.trim();
    if (!subject) return;
    setDraft("");
    void createTask(departmentId, subject);
  };

  const open = tasks.filter((t) => t.status !== "done").length;

  return (
    <div className="tasks-tab">
      <div className="tasks-tab-meta">
        <span>{departmentId}</span>
        <span>{open} open / {tasks.length} total</span>
      </div>
      <div className="task-board-list">
        {tasks.length === 0 && (
          <div className="panel-empty">
            <span className="panel-empty-icon">▦</span>
            no tasks yet
            <span className="panel-empty-hint">add one below — agents see it live</span>
          </div>
        )}
        {tasks.map((t) => {
          const isDone = t.status === "done";
          const isExpanded = expandedId === t.id;
          return (
            <div key={t.id} className={`task-item task-item-${t.status}`}>
              <div
                className={`task-item-subject${isDone ? " task-item-subject-clickable" : ""}`}
                onClick={isDone ? () => setExpandedId(isExpanded ? null : t.id) : undefined}
                role={isDone ? "button" : undefined}
                title={isDone ? "show result" : undefined}
              >
                {isDone && <span className={`task-item-caret${isExpanded ? " task-item-caret-open" : ""}`}>▸</span>}
                {t.subject}
              </div>
              <div className="task-item-meta">
                <span className={`task-status task-status-${t.status}`}>{STATUS_LABEL[t.status]}</span>
                {t.assigneeAgentId && <span className="task-assignee">@{t.assigneeAgentId}</span>}
              </div>
              {isDone && isExpanded && (
                <div className="task-item-result">
                  {t.result ? (
                    <div className="task-item-result-body">{renderResult(t.result)}</div>
                  ) : (
                    <div className="task-item-result-empty">
                      no result was recorded for this task
                    </div>
                  )}
                </div>
              )}
              <div className="task-item-actions">
                {t.status !== "in_progress" && t.status !== "done" && (
                  <button onClick={() => void updateTaskStatus(t.id, "in_progress")}>▶ start</button>
                )}
                {t.status !== "done" && (
                  <button onClick={() => void updateTaskStatus(t.id, "done")}>✓ done</button>
                )}
                {t.status === "done" && (
                  <button onClick={() => void updateTaskStatus(t.id, "open")}>↩ reopen</button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div className="task-board-input">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          placeholder="new task..."
        />
        <button onClick={handleAdd}>add</button>
      </div>
    </div>
  );
}
