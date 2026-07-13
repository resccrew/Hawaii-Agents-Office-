"use client";

import { useEffect, useRef, useState } from "react";
import { useTaskStore, selectTasksFor, connectTaskBoard, createTask, updateTaskStatus } from "@/stores/taskStore";
import type { TaskStatus } from "@/stores/taskStore";

const STATUS_LABEL: Record<TaskStatus, string> = {
  open: "open",
  in_progress: "in progress",
  done: "done",
};

// Structured half of Phase 6 coordination — the shared task board every
// agent in a department (and the human) reads/writes to. No longer a
// stand-alone fixed panel: it renders as the "tasks" tab body inside
// SidePanel, which owns the docked frame/positioning.
export function TaskBoard({ departmentId }: { departmentId: string | null }) {
  const tasks = useTaskStore(selectTasksFor(departmentId ?? ""));
  const [draft, setDraft] = useState("");
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
        {tasks.map((t) => (
          <div key={t.id} className={`task-item task-item-${t.status}`}>
            <div className="task-item-subject">{t.subject}</div>
            <div className="task-item-meta">
              <span className={`task-status task-status-${t.status}`}>{STATUS_LABEL[t.status]}</span>
              {t.assigneeAgentId && <span className="task-assignee">@{t.assigneeAgentId}</span>}
            </div>
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
        ))}
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
