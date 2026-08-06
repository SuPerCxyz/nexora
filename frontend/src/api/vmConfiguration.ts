import { internalRequest } from "./client";
import type { TaskCreated } from "./contracts";

export type VmConfiguration = {
  vm: { name: string; host_id: string; native_id: string; state: string; active: boolean; persistent: boolean };
  base: { resource_id: string; generation: number; persistent_hash: string | null };
  cpu: Record<string, number> | null;
  memory: Record<string, string | number | boolean | null> | null;
  advanced: Record<string, unknown> | null;
  disks: Array<Record<string, string | number | boolean | null>>;
  interfaces: Array<Record<string, string | number | boolean | null>>;
  networks: Array<{ resource_id: string; kind: string; name: string }>;
  storage_volumes: Array<{ resource_id: string; native_id: string; name: string; generation: number; persistent_hash: string | null; pool_name: string; format: string | null; path: string | null; capacity_bytes: number | null; used_by: string | null }>;
  pools: Array<{ resource_id: string; name: string; pool_type: string }>;
  platform_isos: Array<{ id: string; name: string; size_bytes: number; sha256: string }>;
  platform_iso_enabled: boolean;
  host_devices: Array<{ resource_id: string; type: string; name: string; address: string; status: string }>;
  shared_directory_roots: string[];
};

export type ChangePreview = {
  planId: string;
  confirmationToken: string;
  changeType: string;
  diff: string;
};

export function loadVmConfiguration(hostId: string, vmId: string): Promise<VmConfiguration> {
  return internalRequest(`/internal/hosts/${encodeURIComponent(hostId)}/vms/${encodeURIComponent(vmId)}/configuration`);
}

export async function previewVmConfiguration(
  operation: string,
  configuration: VmConfiguration,
  values: Record<string, unknown>,
): Promise<ChangePreview> {
  const path = `/internal/hosts/${encodeURIComponent(configuration.vm.host_id)}`
    + `/vms/${encodeURIComponent(configuration.vm.native_id)}/configuration/preview`;
  const result = await internalRequest<{
    plan_id: string;
    confirmation_token: string;
    change_type: string;
    diff_text: string;
  }>(path, { method: "POST", body: JSON.stringify({ operation, values }) });
  return {
    planId: result.plan_id,
    confirmationToken: result.confirmation_token,
    changeType: result.change_type,
    diff: result.diff_text,
  };
}

export async function applyVmConfiguration(
  configuration: VmConfiguration,
  preview: ChangePreview,
): Promise<string> {
  const path = `/internal/hosts/${encodeURIComponent(configuration.vm.host_id)}`
    + `/vms/${encodeURIComponent(configuration.vm.native_id)}/configuration/apply`;
  const result = await internalRequest<{ location: string }>(path, {
    method: "POST",
    body: JSON.stringify({
      plan_id: preview.planId,
      confirmation_token: preview.confirmationToken,
      change_type: preview.changeType,
    }),
  });
  return result.location;
}

export async function saveVmConfiguration(
  configuration: VmConfiguration,
  operation: string,
  values: Record<string, unknown>,
): Promise<TaskCreated> {
  const path = `/internal/hosts/${encodeURIComponent(configuration.vm.host_id)}`
    + `/vms/${encodeURIComponent(configuration.vm.native_id)}/configuration/save`;
  return internalRequest<TaskCreated>(path, {
    method: "POST",
    body: JSON.stringify({ operation, values }),
  });
}

export type VmXmlHistoryItem = {
  id: string;
  created_at: string;
  xml_hash: string;
};

export function loadVmHistory(hostId: string, vmId: string): Promise<{ items: VmXmlHistoryItem[] }> {
  return internalRequest(`/internal/hosts/${encodeURIComponent(hostId)}`
    + `/vms/${encodeURIComponent(vmId)}/configuration/history`);
}

export function rollbackVmConfiguration(hostId: string, vmId: string, historyId: string): Promise<TaskCreated> {
  return internalRequest<TaskCreated>(`/internal/hosts/${encodeURIComponent(hostId)}`
    + `/vms/${encodeURIComponent(vmId)}/configuration/rollback`, {
    method: "POST",
    body: JSON.stringify({ history_id: historyId }),
  });
}
