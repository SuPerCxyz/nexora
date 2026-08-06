import { internalRequest } from "./client";
import type {
  HostDetail,
  GuestAgentSummary,
  HostSummary,
  OverviewSummary,
  PaginatedResponse,
  VmDetail,
  VmCreateOptions,
  VmCreatePreview,
  VmCreatePreviewRequest,
  VmBlankCreateOptions,
  VmBlankCreatePreview,
  VmBlankCreatePreviewRequest,
  VmRemovePreview,
  TaskCreated,
  VmSummary,
  VmLifecycleAction,
} from "./contracts";

export function loadOverview(): Promise<OverviewSummary> {
  return internalRequest<OverviewSummary>("/internal/overview");
}

export function loadHosts(page: number, pageSize: number): Promise<PaginatedResponse<HostSummary>> {
  return internalRequest<PaginatedResponse<HostSummary>>(
    `/internal/hosts?page=${page}&page_size=${pageSize}`,
  );
}

export function loadVms(
  page: number,
  pageSize: number,
  state?: string,
  hostId?: string,
): Promise<PaginatedResponse<VmSummary>> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (state) query.set("state", state);
  if (hostId) query.set("host_id", hostId);
  return internalRequest<PaginatedResponse<VmSummary>>(`/internal/vms?${query.toString()}`);
}

export function loadHostDetail(hostId: string): Promise<HostDetail> {
  return internalRequest<HostDetail>(`/internal/hosts/${encodeURIComponent(hostId)}`);
}

export function scanHost(hostId: string): Promise<TaskCreated> {
  return internalRequest<TaskCreated>(`/internal/hosts/${encodeURIComponent(hostId)}/scan`, {
    method: "POST",
  });
}

export function loadVmDetail(hostId: string, vmId: string): Promise<VmDetail> {
  return internalRequest<VmDetail>(
    `/internal/hosts/${encodeURIComponent(hostId)}/vms/${encodeURIComponent(vmId)}`,
  );
}

export function loadGuestAgent(hostId: string, vmId: string): Promise<GuestAgentSummary> {
  return internalRequest<GuestAgentSummary>(
    `/internal/hosts/${encodeURIComponent(hostId)}/vms/${encodeURIComponent(vmId)}/guest-agent`,
  );
}

export function submitVmLifecycle(
  hostId: string,
  vmId: string,
  action: VmLifecycleAction,
  confirmationName?: string,
): Promise<TaskCreated> {
  return internalRequest<TaskCreated>(
    `/internal/hosts/${encodeURIComponent(hostId)}/vms/${encodeURIComponent(vmId)}/lifecycle`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, confirmation_name: confirmationName }),
    },
  );
}

export function loadVmCreateOptions(): Promise<VmCreateOptions> {
  return internalRequest<VmCreateOptions>("/internal/vm-create/options");
}

export function previewVmCreate(submitted: VmCreatePreviewRequest): Promise<VmCreatePreview> {
  return internalRequest<VmCreatePreview>("/internal/vm-create/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submitted),
  });
}

export function applyVmCreate(preview: VmCreatePreview): Promise<TaskCreated> {
  return internalRequest<TaskCreated>("/internal/vm-create/apply", {
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

export function loadVmBlankCreateOptions(): Promise<VmBlankCreateOptions> {
  return internalRequest<VmBlankCreateOptions>("/internal/vm-create/blank-disk/options");
}

export function previewVmBlankCreate(
  submitted: VmBlankCreatePreviewRequest,
): Promise<VmBlankCreatePreview> {
  return internalRequest<VmBlankCreatePreview>("/internal/vm-create/blank-disk/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submitted),
  });
}

export function applyVmBlankCreate(preview: VmBlankCreatePreview): Promise<TaskCreated> {
  return internalRequest<TaskCreated>("/internal/vm-create/blank-disk/apply", {
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

export type VmRemoveRequest = {
  operation: string;
  target_name?: string;
  remove_disks?: boolean;
  remove_nvram?: boolean;
};

export function previewVmRemove(
  hostId: string,
  vmId: string,
  submitted: VmRemoveRequest,
): Promise<VmRemovePreview> {
  return internalRequest<VmRemovePreview>(removePath(hostId, vmId, "preview"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submitted),
  });
}

export function applyVmRemove(
  hostId: string,
  vmId: string,
  preview: VmRemovePreview,
  confirmationName: string,
): Promise<TaskCreated> {
  return internalRequest<TaskCreated>(removePath(hostId, vmId, "apply"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      plan_id: preview.plan_id,
      confirmation_token: preview.confirmation_token,
      confirmation_name: confirmationName,
    }),
  });
}

function removePath(hostId: string, vmId: string, step: string) {
  return `/internal/hosts/${encodeURIComponent(hostId)}`
    + `/vms/${encodeURIComponent(vmId)}/remove/${step}`;
}
