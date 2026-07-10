"use client";

import { create } from "zustand";

export type TaskStatus = "open" | "in_progress" | "done";

export interface SharedTask {
  id: string;
  departmentId: string;
  subject: string;
  description: string | null;
  status: TaskStatus;
  assigneeAgentId: string | null;
  createdByAgentId: string | null;
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

export function connectTaskBoard(departmentId: string, baseUrl = "ws://localhost:8010"): () => void {
  const ws = new WebSocket(`${baseUrl}/ws/tasks/${departmentId}`);
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "task_board_update") {
        useTaskStore.getState().setTasks(departmentId, msg.tasks);
      }
    } catch {
      // ignore malformed frames
    }
  };
  return () => ws.close();
}

export async function createTask(
  departmentId: string,
  subject: string,
  apiBase = "http://localhost:8010",
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
  apiBase = "http://localhost:8010",
): Promise<void> {
  await fetch(`${apiBase}/api/v1/tasks/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}
