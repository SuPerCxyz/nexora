import { internalRequest } from "./client";
import type { TaskCreated } from "./contracts";

export type HostRemovalPreview = {
  plan_id: string;
  confirmation_token: string;
  host_id: string;
  host_name: string;
  mode: string;
  paths: string[];
  units: string[];
  warnings: string[];
};

export function previewHostRemoval(hostId: string, mode: string): Promise<HostRemovalPreview> {
  return post(`/internal/hosts/${encodeURIComponent(hostId)}/removal/preview`, { mode });
}

export function applyHostRemoval(preview: HostRemovalPreview, confirmationName: string): Promise<TaskCreated> {
  return post(`/internal/hosts/${encodeURIComponent(preview.host_id)}/removal/apply`, {
    plan_id: preview.plan_id,
    confirmation_token: preview.confirmation_token,
    confirmation_name: confirmationName,
  });
}

function post<T>(path: string, body: unknown): Promise<T> {
  return internalRequest(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
