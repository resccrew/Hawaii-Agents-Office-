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
// agent in a department (and the human) reads/writes to, complementary
// to direct agent-to-agent chat via ChatPanel. Same panel styling as
// ChatPanel.tsx (pixel-frame, sunset header) for visual consistency.
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

  return (
    <div className="task-board pixel-frame">
      <div className="task-board-header">tasks — {departmentId}</div>
      <div className="task-board-list">
        {tasks.length === 0 && <div className="task-board-empty">no tasks yet</div>}
        {tasks.map((t) => (
          <div key={t.id} className={`task-item task-item-${t.status}`}>
            <div className="task-item-subject">{t.subject}</div>
            <div className="task-item-meta">
              <span>{STATUS_LABEL[t.status]}</span>
              {t.assigneeAgentId && <span>· {t.assigneeAgentId}</span>}
            </div>
            <div className="task-item-actions">
              {t.status !== "in_progress" && (
                <button onClick={() => void updateTaskStatus(t.id, "in_progress")}>start</button>
              )}
              {t.status !== "done" && (
                <button onClick={() => void updateTaskStatus(t.id, "done")}>done</button>
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
