import { Flex, Select, Space, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import type {
  StorageChangePreview,
  StorageOverview,
  StoragePoolCreateRequest,
  StoragePoolSummary,
  StorageVolumeCreateRequest,
} from "../api/contracts";
import {
  applyStoragePool,
  applyStorageMutation,
  applyStorageVolume,
  changeStoragePoolLifecycle,
  loadStorage,
  previewStoragePool,
  previewStorageMutation,
  previewStorageVolume,
} from "../api/storage";
import { PageError, PageLoading } from "./PageState";
import { navigateToTask } from "./navigateToTask";
import { StorageChangePreviewModal } from "./StorageChangePreviewModal";
import { StorageCreatePanel } from "./StorageCreatePanel";
import { StorageTables } from "./StorageTables";

const ALL_HOSTS = "__all__";

export function StoragePage() {
  const [storage, setStorage] = useState<StorageOverview | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [preview, setPreview] = useState<StorageChangePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedHostId, setSelectedHostId] = useState<string | undefined>(undefined);

  useEffect(() => { loadStorage().then(setStorage).catch(setError); }, []);

  const selectedHostIdResolved = selectedHostId ?? ALL_HOSTS;

  const visible = useMemo(() => {
    if (!storage) return { pools: [], volumes: [] };
    if (selectedHostIdResolved === ALL_HOSTS) return { pools: storage.pools, volumes: storage.volumes };
    return {
      pools: storage.pools.filter((item) => item.host_id === selectedHostIdResolved),
      volumes: storage.volumes.filter((item) => item.host_id === selectedHostIdResolved),
    };
  }, [storage, selectedHostIdResolved]);

  async function makePreview(request: StoragePoolCreateRequest | StorageVolumeCreateRequest, kind: "pool" | "volume") {
    setLoading(true); setActionError(null);
    try { setPreview(await (kind === "pool" ? previewStoragePool(request as StoragePoolCreateRequest) : previewStorageVolume(request as StorageVolumeCreateRequest))); }
    catch (caught) { setActionError(errorText(caught)); }
    finally { setLoading(false); }
  }

  async function applyPreview() {
    if (!preview) return;
    setLoading(true); setActionError(null);
    try {
      const task = await (
        preview.operation === "pool_create"
          ? applyStoragePool(preview)
          : preview.operation === "volume_create"
            ? applyStorageVolume(preview)
            : applyStorageMutation(preview)
      );
      navigateToTask(task.location);
    } catch (caught) { setActionError(errorText(caught)); setLoading(false); }
  }

  async function lifecycle(pool: StoragePoolSummary, action: string) {
    setLoading(true); setActionError(null);
    try { const task = await changeStoragePoolLifecycle(pool.resource_id, action); navigateToTask(task.location); }
    catch (caught) { setActionError(errorText(caught)); setLoading(false); }
  }

  async function mutation(resourceId: string, operation: "pool_delete" | "volume_resize" | "volume_delete", targetCapacityGib?: number) {
    setLoading(true); setActionError(null);
    try { setPreview(await previewStorageMutation(resourceId, operation, targetCapacityGib)); }
    catch (caught) { setActionError(errorText(caught)); }
    finally { setLoading(false); }
  }

  if (error) return <PageError error={error} />;
  if (!storage) return <PageLoading />;
  return (
    <Space className="nx-page-stack" orientation="vertical" size={12}>
      <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap>
        <div className="nx-page-title">
          <Typography.Title level={2}>存储</Typography.Title>
          <Typography.Text type="secondary">以节点为维度管理存储池与存储卷，仅可写范围包含已纳管的本地目录与 NFS netfs Pool。</Typography.Text>
        </div>
        <Flex align="center" gap={8}>
          <Typography.Text type="secondary">节点</Typography.Text>
          <Select
            className="nx-filter-control"
            style={{ width: 220 }}
            value={selectedHostId}
            placeholder="全部节点"
            options={[{ value: ALL_HOSTS, label: "全部节点" }, ...storage.hosts.map((host) => ({ value: host.id, label: host.name }))]}
            onChange={(value: string | undefined) => setSelectedHostId(value === ALL_HOSTS ? undefined : value)}
          />
        </Flex>
      </Flex>
      <StorageCreatePanel storage={storage} selectedHostId={selectedHostIdResolved} loading={loading} error={preview ? null : actionError} onPoolPreview={(value) => makePreview(value, "pool")} onVolumePreview={(value) => makePreview(value, "volume")} />
      <StorageTables pools={visible.pools} volumes={visible.volumes} loading={loading} onLifecycle={lifecycle} onMutation={mutation} />
      <StorageChangePreviewModal preview={preview} loading={loading} error={preview ? actionError : null} onCancel={() => { setPreview(null); setActionError(null); }} onConfirm={applyPreview} />
    </Space>
  );
}

function errorText(caught: unknown): string {
  return caught instanceof Error ? caught.message : "存储操作失败";
}
