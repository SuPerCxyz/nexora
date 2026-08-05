import type {
  StorageChangePreview,
  StorageOverview,
  StoragePoolCreateRequest,
  StorageVolumeCreateRequest,
  TaskCreated,
} from "./contracts";
import { internalRequest } from "./client";

export function loadStorage(): Promise<StorageOverview> {
  return internalRequest<StorageOverview>("/internal/storage");
}

export function previewStoragePool(
  submitted: StoragePoolCreateRequest,
): Promise<StorageChangePreview> {
  return post<StorageChangePreview>("/internal/storage/pools/preview", submitted);
}

export function applyStoragePool(preview: StorageChangePreview): Promise<TaskCreated> {
  return post<TaskCreated>("/internal/storage/pools/apply", scope(preview));
}

export function previewStorageVolume(
  submitted: StorageVolumeCreateRequest,
): Promise<StorageChangePreview> {
  return post<StorageChangePreview>("/internal/storage/volumes/preview", submitted);
}

export function applyStorageVolume(preview: StorageChangePreview): Promise<TaskCreated> {
  return post<TaskCreated>("/internal/storage/volumes/apply", scope(preview));
}

export function changeStoragePoolLifecycle(
  resourceId: string,
  action: string,
): Promise<TaskCreated> {
  return post<TaskCreated>("/internal/storage/pools/lifecycle", {
    resource_id: resourceId,
    action,
  });
}

export function previewStorageMutation(
  resourceId: string,
  operation: "pool_delete" | "volume_resize" | "volume_delete",
  targetCapacityGib?: number,
): Promise<StorageChangePreview> {
  return post<StorageChangePreview>("/internal/storage/mutations/preview", {
    resource_id: resourceId,
    operation,
    target_capacity_gib: targetCapacityGib,
  });
}

export function applyStorageMutation(preview: StorageChangePreview): Promise<TaskCreated> {
  return post<TaskCreated>("/internal/storage/mutations/apply", {
    ...scope(preview),
    operation: preview.operation,
  });
}

function scope(preview: StorageChangePreview) {
  return {
    plan_id: preview.plan_id,
    confirmation_token: preview.confirmation_token,
    host_id: preview.host_id,
    pool_uuid: preview.pool_uuid,
  };
}

function post<T>(path: string, body: object): Promise<T> {
  return internalRequest<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
