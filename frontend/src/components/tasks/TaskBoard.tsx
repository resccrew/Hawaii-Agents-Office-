"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  useTaskStore,
  selectTasksFor,
  connectTaskBoard,
  createTask,
  updateTaskStatus,
  dispatchTask,
  type SharedTask,
} from "@/stores/taskStore";
import type { TaskStatus } from "@/stores/taskStore";
import { useAgentsStore, selectAgents } from "@/stores/agentsStore";

const STATUS_LABEL: Record<TaskStatus, string> = {
  open: "open",
  in_progress: "in progress",
  done: "done",
};

const COLUMNS: TaskStatus[] = ["open", "in_progress", "done"];

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

// One card in a kanban column. Native HTML5 drag-and-drop (draggable +
// dragstart carrying the task id) — no drag library needed for a single
// 3-column board with no in-column reordering.
function TaskCard({
  task,
  assigneeName,
  isExpanded,
  onToggleExpand,
  onDragStart,
}: {
  task: SharedTask;
  assigneeName: string | null;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onDragStart: (e: React.DragEvent) => void;
}) {
  const isDone = task.status === "done";
  return (
    <div
      className={`task-item task-item-${task.status}`}
      draggable={!isDone}
      onDragStart={onDragStart}
    >
      <div
        className={`task-item-subject${isDone ? " task-item-subject-clickable" : ""}`}
        onClick={isDone ? onToggleExpand : undefined}
        role={isDone ? "button" : undefined}
        title={isDone ? "show result" : undefined}
      >
        {isDone && <span className={`task-item-caret${isExpanded ? " task-item-caret-open" : ""}`}>▸</span>}
        {task.subject}
      </div>
      {(task.assigneeAgentId || isDone) && (
        <div className="task-item-meta">
          {task.assigneeAgentId && (
            <span className="task-assignee">@{assigneeName ?? task.assigneeAgentId}</span>
          )}
        </div>
      )}
      {isDone && isExpanded && (
        <div className="task-item-result">
          {task.result ? (
            <div className="task-item-result-body">{renderResult(task.result)}</div>
          ) : (
            <div className="task-item-result-empty">no result was recorded for this task</div>
          )}
        </div>
      )}
      <div className="task-item-actions">
        {task.status === "done" && <button onClick={() => void updateTaskStatus(task.id, "open")}>↩ reopen</button>}
        {task.status === "in_progress" && (
          <button onClick={() => void updateTaskStatus(task.id, "done")}>✓ done</button>
        )}
      </div>
    </div>
  );
}

// Structured half of Phase 6 coordination — the shared task board every
// agent in a department (and the human) reads/writes to. Rewritten from a
// flat filtered list into real kanban columns: dragging a card into
// "in progress" dispatches a coding agent against it (POST
// /tasks/{id}/dispatch), rather than just changing status locally — the
// WS broadcast is the source of truth, so the card only actually moves once
// the backend confirms (no optimistic UI, same convention the store already
// used for updateTaskStatus).
export function TaskBoard({ departmentId }: { departmentId: string | null }) {
  const tasks = useTaskStore(selectTasksFor(departmentId ?? ""));
  const agents = useAgentsStore(selectAgents);
  const [draft, setDraft] = useState("");
  // Which done task is expanded to show its result report. Only one at a time.
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<TaskStatus | null>(null);
  const [dispatchError, setDispatchError] = useState<string | null>(null);
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

  const handleDrop = (column: TaskStatus) => (e: React.DragEvent) => {
    e.preventDefault();
    setDragOverColumn(null);
    const taskId = e.dataTransfer.getData("text/plain");
    if (!taskId) return;
    const task = tasks.find((t) => t.id === taskId);
    if (!task || task.status === column) return;

    if (column === "in_progress") {
      if (task.assigneeAgentId) {
        // Already has an agent — just move it, don't spawn a second one.
        void updateTaskStatus(taskId, "in_progress");
      } else {
        setDispatchError(null);
        void dispatchTask(taskId).catch((err) => setDispatchError(err instanceof Error ? err.message : String(err)));
      }
    } else {
      void updateTaskStatus(taskId, column);
    }
  };

  const open = tasks.filter((t) => t.status !== "done").length;

  return (
    <div className="tasks-tab">
      <div className="tasks-tab-meta">
        <span>{departmentId}</span>
        <span>{open} open / {tasks.length} total</span>
      </div>
      {dispatchError && (
        <div className="task-dispatch-error">
          {dispatchError}
          <button onClick={() => setDispatchError(null)} aria-label="dismiss">✕</button>
        </div>
      )}
      <div className="kanban-board">
        {COLUMNS.map((column) => {
          const columnTasks = tasks.filter((t) => t.status === column);
          return (
            <div
              key={column}
              className={`kanban-column${dragOverColumn === column ? " kanban-column-dragover" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOverColumn(column);
              }}
              onDragLeave={() => setDragOverColumn((c) => (c === column ? null : c))}
              onDrop={handleDrop(column)}
            >
              <div className="kanban-column-header">
                <span>{STATUS_LABEL[column]}</span>
                <span className="kanban-column-count">{columnTasks.length}</span>
              </div>
              <div className="kanban-column-list">
                {columnTasks.length === 0 && (
                  <div className="panel-empty panel-empty-compact">
                    {column === "open" ? "no tasks yet" : "drop a card here"}
                  </div>
                )}
                {columnTasks.map((t) => (
                  <TaskCard
                    key={t.id}
                    task={t}
                    assigneeName={agents.find((a) => a.agentId === t.assigneeAgentId)?.name ?? null}
                    isExpanded={expandedId === t.id}
                    onToggleExpand={() => setExpandedId((id) => (id === t.id ? null : t.id))}
                    onDragStart={(e) => e.dataTransfer.setData("text/plain", t.id)}
                  />
                ))}
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
