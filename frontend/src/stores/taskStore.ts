"use client";

import { create } from "zustand";
import { getHttpBase, getWsBase } from "@/systems/backendUrl";
import { connectWithRetry } from "@/systems/reconnectingWebSocket";

export type TaskStatus = "open" | "in_progress" | "done";

export interface SharedTask {
  id: string;
  departmentId: string;
  subject: string;
  description: string | null;
  status: TaskStatus;
  assigneeAgentId: string | null;
  createdByAgentId: string | null;
  result: string | null;
  createdAt: string;
  updatedAt: string;
}

interface TaskStore {
  tasksByDepartment: Map<string, SharedTask[]>;
  setTasks: (departmentId: string, tasks: SharedTask[]) => void;
}

export const useTaskStore = create<TaskStore>()((set) => ({
  tasksByDepartment: new Map(),
  setTasks: (departmentId, tasks) =>
    set((state) => {
      const next = new Map(state.tasksByDepartment);
      next.set(departmentId, tasks);
      return { tasksByDepartment: next };
    }),
}));

const EMPTY_TASKS: SharedTask[] = [];
export const selectTasksFor = (departmentId: string) => (state: TaskStore) =>
  state.tasksByDepartment.get(departmentId) ?? EMPTY_TASKS;

// Bugfix: now auto-reconnects instead of the task board going silently
// stale on any connection drop.
export function connectTaskBoard(departmentId: string, baseUrl = getWsBase()): () => void {
  return connectWithRetry(`${baseUrl}/ws/tasks/${departmentId}`, {
    onMessage: (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "task_board_update") {
          useTaskStore.getState().setTasks(departmentId, msg.tasks);
        }
      } catch {
        // ignore malformed frames
      }
    },
  });
}

export async function createTask(
  departmentId: string,
  subject: string,
  apiBase = getHttpBase(),
): Promise<void> {
  await fetch(`${apiBase}/api/v1/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ department_id: departmentId, subject }),
  });
}

export async function updateTaskStatus(
  taskId: string,
  status: TaskStatus,
  apiBase = getHttpBase(),
): Promise<void> {
  await fetch(`${apiBase}/api/v1/tasks/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

// Kanban drag-to-dispatch: spawns a coding agent against a task and moves
// it to in_progress server-side. Errors (e.g. already dispatched) surface
// to the caller instead of being swallowed — the board doesn't optimistically
// move the card, so the caller should show the error if this rejects.
export async function dispatchTask(
  taskId: string,
  apiBase = getHttpBase(),
): Promise<void> {
  const res = await fetch(`${apiBase}/api/v1/tasks/${taskId}/dispatch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `dispatch failed: HTTP ${res.status}`);
  }
}
