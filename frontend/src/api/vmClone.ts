import { internalRequest } from "./client";

export type VmClonePreview = {
  plan_id: string;
  confirmation_token: string;
  target_host_id: string;
  target_vm_uuid: string;
  target_name: string;
  file_count: number;
  diff_text: string;
};

export type VmMigratePreview = {
  plan_id: string;
  confirmation_token: string;
  target_host_id: string;
  target_vm_uuid: string;
  target_name: string;
  file_count: number;
  preserve_identity: boolean;
  diff_text: string;
};

export function previewVmClone(
  hostId: string,
  vmId: string,
  targetPoolId: string,
  targetName: string,
): Promise<VmClonePreview> {
  return internalRequest(path(hostId, vmId, "clone", "preview"), {
    method: "POST",
    body: JSON.stringify({ target_pool_id: targetPoolId, target_name: targetName }),
  });
}

export function applyVmClone(
  hostId: string,
  vmId: string,
  preview: VmClonePreview,
): Promise<{ location: string }> {
  return internalRequest(path(hostId, vmId, "clone", "apply"), {
    method: "POST",
    body: JSON.stringify({
      plan_id: preview.plan_id,
      confirmation_token: preview.confirmation_token,
    }),
  });
}

export function previewVmMigrate(
  hostId: string,
  vmId: string,
  targetPoolId: string,
): Promise<VmMigratePreview> {
  return internalRequest(path(hostId, vmId, "migrate", "preview"), {
    method: "POST",
    body: JSON.stringify({ target_pool_id: targetPoolId }),
  });
}

export function applyVmMigrate(
  hostId: string,
  vmId: string,
  preview: VmMigratePreview,
): Promise<{ location: string }> {
  return internalRequest(path(hostId, vmId, "migrate", "apply"), {
    method: "POST",
    body: JSON.stringify({
      plan_id: preview.plan_id,
      confirmation_token: preview.confirmation_token,
    }),
  });
}

function path(hostId: string, vmId: string, action: string, step: string) {
  return `/internal/hosts/${encodeURIComponent(hostId)}`
    + `/vms/${encodeURIComponent(vmId)}/${action}/${step}`;
}
