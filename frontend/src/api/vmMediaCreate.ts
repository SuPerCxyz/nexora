import type {
  TaskCreated,
  VmMediaCreateOptions,
  VmMediaCreatePreview,
  VmMediaCreatePreviewRequest,
} from "./contracts";
import { internalRequest } from "./client";

export function loadVmMediaCreateOptions(): Promise<VmMediaCreateOptions> {
  return internalRequest<VmMediaCreateOptions>("/internal/vm-create/platform-image/options");
}

export function previewVmMediaCreate(
  submitted: VmMediaCreatePreviewRequest,
): Promise<VmMediaCreatePreview> {
  return internalRequest<VmMediaCreatePreview>("/internal/vm-create/platform-image/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submitted),
  });
}

export function applyVmMediaCreate(preview: VmMediaCreatePreview): Promise<TaskCreated> {
  return internalRequest<TaskCreated>("/internal/vm-create/platform-image/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      plan_id: preview.plan_id,
      confirmation_token: preview.confirmation_token,
      host_id: preview.host_id,
      vm_uuid: preview.vm_uuid,
    }),
  });
}
