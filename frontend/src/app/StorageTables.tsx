import { Button, Card, Dropdown, Flex, InputNumber, Modal, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type { StoragePoolSummary, StorageVolumeSummary } from "../api/contracts";
import { formatBytes } from "./format";
import { StatusTag } from "./StatusTag";

export function StorageTables({
  pools,
  volumes,
  loading,
  onLifecycle,
  onMutation,
}: {
  pools: StoragePoolSummary[];
  volumes: StorageVolumeSummary[];
  loading: boolean;
  onLifecycle: (pool: StoragePoolSummary, action: string) => void;
  onMutation: (resourceId: string, operation: "pool_delete" | "volume_resize" | "volume_delete", targetCapacityGib?: number) => void;
}) {
  const poolColumns: ColumnsType<StoragePoolSummary> = [
    { title: "存储池", render: (_, pool) => <ResourceIdentity name={pool.name} identity={pool.native_id} /> },
    { title: "节点", dataIndex: "host_name" },
    { title: "类型", dataIndex: "pool_type", render: (value) => <code>{value}</code> },
    { title: "状态", render: (_, pool) => <PoolState pool={pool} /> },
    { title: "Target", dataIndex: "target_path", render: (value) => <code>{value ?? "—"}</code> },
    { title: "可用容量", dataIndex: "available_bytes", render: (v: number | null) => <span className="nx-number-unit">{formatBytes(v, { fixedUnit: "GiB" })}</span> },
    { title: "操作", width: 100, render: (_, pool) => pool.writable ? <PoolActions pool={pool} loading={loading} onLifecycle={onLifecycle} onDelete={() => onMutation(pool.resource_id, "pool_delete")} /> : <Typography.Text type="secondary">只读</Typography.Text> },
  ];
  const volumeColumns: ColumnsType<StorageVolumeSummary> = [
    { title: "存储卷", render: (_, volume) => <ResourceIdentity name={volume.name} identity={volume.resource_id} /> },
    { title: "节点 / Pool", render: (_, volume) => `${volume.host_name} / ${volume.pool_name}` },
    { title: "格式", dataIndex: "format", render: (value) => <code>{value ?? "—"}</code> },
    { title: "容量", dataIndex: "capacity_bytes", render: (v: number | null) => <span className="nx-number-unit">{formatBytes(v, { fixedUnit: "GiB" })}</span> },
    { title: "分配", dataIndex: "allocation_bytes", render: (v: number | null) => <span className="nx-number-unit">{formatBytes(v, { fixedUnit: "GiB" })}</span> },
    { title: "状态", render: (_, volume) => <Flex gap={6} className="nx-inline-tags"><StatusTag label={volume.in_use ? "使用中" : "未使用"} tone={volume.in_use ? "running" : "stopped"} />{!volume.writable && <StatusTag label="只读" tone="unknown" />}</Flex> },
    { title: "操作", width: 100, render: (_, volume) => volume.writable ? <VolumeActions volume={volume} loading={loading} onMutation={onMutation} /> : <Typography.Text type="secondary">只读</Typography.Text> },
  ];
  return (
    <Space className="nx-page-stack" orientation="vertical" size={12}>
      <Card title="已发现的存储池">
        <Table className="nx-responsive-table" rowKey="resource_id" columns={poolColumns} dataSource={pools} pagination={{ pageSize: 20 }} scroll={{ x: 900 }} tableLayout="fixed" />
      </Card>
      <Card title="已发现的存储卷">
        <Table className="nx-responsive-table" rowKey="resource_id" columns={volumeColumns} dataSource={volumes} pagination={{ pageSize: 20 }} scroll={{ x: 800 }} tableLayout="fixed" />
      </Card>
    </Space>
  );
}

function PoolActions({ pool, loading, onLifecycle, onDelete }: { pool: StoragePoolSummary; loading: boolean; onLifecycle: (pool: StoragePoolSummary, action: string) => void; onDelete: () => void }) {
  const items = [
    { key: "start", label: "启动", disabled: pool.active },
    { key: "stop", label: "停止（保留文件）", disabled: !pool.active },
    { key: "refresh", label: "刷新", disabled: !pool.active },
    { key: "autostart_enable", label: "启用自动启动", disabled: pool.autostart },
    { key: "autostart_disable", label: "禁用自动启动", disabled: !pool.autostart, danger: true },
    { key: "delete", label: "移除存储池定义", disabled: pool.active, danger: true },
  ];
  return <Dropdown menu={{ items, onClick: ({ key }) => key === "delete" ? onDelete() : onLifecycle(pool, key) }} trigger={["click"]} disabled={loading}><Button size="small" className="nx-btn-info">操作</Button></Dropdown>;
}

function VolumeActions({ volume, loading, onMutation }: {
  volume: StorageVolumeSummary;
  loading: boolean;
  onMutation: (resourceId: string, operation: "volume_resize" | "volume_delete", targetCapacityGib?: number) => void;
}) {
  const resize = () => {
    let target = Math.ceil((volume.capacity_bytes ?? 0) / 1024 ** 3) + 1;
    Modal.confirm({
      title: `扩容 ${volume.name}`,
      content: <InputNumber min={target} defaultValue={target} addonAfter="GiB" onChange={(value) => { if (value) target = value; }} />,
      okText: "生成扩容预览",
      onOk: () => onMutation(volume.resource_id, "volume_resize", target),
    });
  };
  const items = [
    { key: "resize", label: "扩容" },
    { key: "delete", label: "删除", danger: true },
  ];
  return <Dropdown menu={{ items, onClick: ({ key }) => key === "resize" ? resize() : onMutation(volume.resource_id, "volume_delete") }} disabled={loading}><Button size="small" className="nx-btn-info">操作</Button></Dropdown>;
}

function PoolState({ pool }: { pool: StoragePoolSummary }) {
  return <Flex gap={6} className="nx-inline-tags"><StatusTag label={pool.active ? "运行中" : "已停止"} tone={pool.active ? "running" : "stopped"} />{pool.autostart && <StatusTag label="自动启动" tone="starting" />}</Flex>;
}

function ResourceIdentity({ name, identity }: { name: string; identity: string }) {
  return <div><strong>{name}</strong><small className="nx-technical">{identity}</small></div>;
}
