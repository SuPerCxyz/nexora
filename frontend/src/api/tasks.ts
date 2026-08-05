import { internalRequest } from "./client";
import type { TaskCreated, TaskDetail, TaskSummary } from "./contracts";

export function loadTasks(): Promise<{ items: TaskSummary[] }> {
  return internalRequest<{ items: TaskSummary[] }>("/internal/tasks");
}

export function loadTask(taskId: string): Promise<TaskDetail> {
  return internalRequest<TaskDetail>(`/internal/tasks/${encodeURIComponent(taskId)}`);
}

export function cancelTask(taskId: string): Promise<TaskCreated> {
  return internalRequest<TaskCreated>(`/internal/tasks/${encodeURIComponent(taskId)}/cancel`, {
    method: "POST",
  });
}

export function recoverTask(taskId: string): Promise<TaskCreated> {
  return internalRequest<TaskCreated>(`/internal/tasks/${encodeURIComponent(taskId)}/recover`, {
    method: "POST",
  });
}
