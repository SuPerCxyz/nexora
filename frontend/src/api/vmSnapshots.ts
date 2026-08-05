import { internalRequest } from "./client";

export type SnapshotOperation = "create" | "delete" | "revert";

export type SnapshotPreview = {
  planId: string;
  confirmationToken: string;
  operation: SnapshotOperation;
  snapshotName: string;
  diffText: string;
};

export async function previewSnapshot(
  hostId: string,
  vmId: string,
  values: {
    operation: SnapshotOperation;
    name: string;
    description?: string;
    snapshot_resource_id?: string;
  },
): Promise<SnapshotPreview> {
  const response = await internalRequest<{
    plan_id: string;
    confirmation_token: string;
    operation: SnapshotOperation;
    snapshot_name: string;
    diff_text: string;
  }>(path(hostId, vmId, "preview"), {
    method: "POST",
    body: JSON.stringify(values),
  });
  return {
    planId: response.plan_id,
    confirmationToken: response.confirmation_token,
    operation: response.operation,
    snapshotName: response.snapshot_name,
    diffText: response.diff_text,
  };
}

export async function applySnapshot(
  hostId: string,
  vmId: string,
  preview: SnapshotPreview,
  confirmationName?: string,
): Promise<string> {
  const response = await internalRequest<{ location: string }>(path(hostId, vmId, "apply"), {
    method: "POST",
    body: JSON.stringify({
      operation: preview.operation,
      plan_id: preview.planId,
      confirmation_token: preview.confirmationToken,
      snapshot_name: preview.snapshotName,
      confirmation_name: confirmationName,
    }),
  });
  return response.location;
}

function path(hostId: string, vmId: string, action: string) {
  return `/internal/hosts/${encodeURIComponent(hostId)}`
    + `/vms/${encodeURIComponent(vmId)}/snapshots/${action}`;
}
