import { Alert, Button, Card, Checkbox, Form, Input, InputNumber, Select, Tabs } from "antd";
import { useState } from "react";

import type {
  StorageOverview,
  StoragePoolCreateRequest,
  StorageVolumeCreateRequest,
} from "../api/contracts";

export function StorageCreatePanel({
  storage,
  loading,
  error,
  onPoolPreview,
  onVolumePreview,
}: {
  storage: StorageOverview;
  loading: boolean;
  error: string | null;
  onPoolPreview: (request: StoragePoolCreateRequest) => void;
  onVolumePreview: (request: StorageVolumeCreateRequest) => void;
}) {
  return (
    <Card title="创建资源">
      {error && <Alert className="nx-section-alert" type="error" showIcon title="无法检查存储配置" description={error} />}
      <Tabs items={[
        { key: "pool", label: "存储池", children: <PoolForm hosts={storage.hosts} loading={loading} onSubmit={onPoolPreview} /> },
        { key: "volume", label: "存储卷", children: <VolumeForm pools={storage.pools.filter((item) => item.writable && item.active)} loading={loading} onSubmit={onVolumePreview} /> },
      ]} />
    </Card>
  );
}

function PoolForm({
  hosts,
  loading,
  onSubmit,
}: {
  hosts: StorageOverview["hosts"];
  loading: boolean;
  onSubmit: (request: StoragePoolCreateRequest) => void;
}) {
  const [poolType, setPoolType] = useState("dir");
  return (
    <Form
      layout="vertical"
      requiredMark="optional"
      initialValues={{ pool_type: "dir", nfs_version: "4", start: true, autostart: true }}
      onFinish={(values) => onSubmit({
        host_id: values.host_id,
        name: values.name,
        pool_type: values.pool_type,
        target_path: values.target_path,
        source_host: poolType === "netfs" ? values.source_host : null,
        source_path: poolType === "netfs" ? values.source_path : null,
        nfs_version: poolType === "netfs" ? values.nfs_version : null,
        mount_options: poolType === "netfs" ? splitOptions(values.mount_options) : [],
        start: Boolean(values.start),
        autostart: Boolean(values.autostart),
      })}
    >
      <div className="nx-form-grid">
        <Form.Item label="节点" name="host_id" rules={[{ required: true }]}>
          <Select placeholder="选择已就绪节点" options={hosts.map((item) => ({ value: item.id, label: item.name }))} />
        </Form.Item>
        <Form.Item label="名称" name="name" rules={[{ required: true, max: 128 }]}><Input /></Form.Item>
        <Form.Item label="类型" name="pool_type"><Select onChange={setPoolType} options={[{ value: "dir", label: "本地目录" }, { value: "netfs", label: "NFS netfs" }]} /></Form.Item>
        <Form.Item label="目标路径" name="target_path" rules={[{ required: true, max: 1024 }]}><Input className="nx-technical-input" placeholder="/var/lib/libvirt/images" /></Form.Item>
        {poolType === "netfs" && <>
          <Form.Item label="NFS Server" name="source_host" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="Export 路径" name="source_path" rules={[{ required: true }]}><Input className="nx-technical-input" /></Form.Item>
          <Form.Item label="NFS 版本" name="nfs_version"><Select options={[{ value: "4", label: "NFSv4" }, { value: "3", label: "NFSv3" }]} /></Form.Item>
          <Form.Item label="挂载选项" name="mount_options" extra="仅允许受控 ro/rw、soft/hard 和数值选项。"><Input placeholder="rw,hard,timeo=600" /></Form.Item>
        </>}
      </div>
      <div className="nx-check-row">
        <Form.Item name="start" valuePropName="checked" noStyle><Checkbox>立即启动</Checkbox></Form.Item>
        <Form.Item name="autostart" valuePropName="checked" noStyle><Checkbox>自动启动</Checkbox></Form.Item>
      </div>
      <div className="nx-form-actions nx-form-actions-end"><Button type="primary" htmlType="submit" loading={loading}>检查创建配置</Button></div>
    </Form>
  );
}

function VolumeForm({
  pools,
  loading,
  onSubmit,
}: {
  pools: StorageOverview["pools"];
  loading: boolean;
  onSubmit: (request: StorageVolumeCreateRequest) => void;
}) {
  return (
    <Form layout="vertical" requiredMark="optional" initialValues={{ volume_format: "qcow2", capacity_gib: 20 }} onFinish={onSubmit}>
      <div className="nx-form-grid">
        <Form.Item label="目标 Pool" name="pool_resource_id" rules={[{ required: true }]}>
          <Select placeholder="选择 active managed Pool" options={pools.map((item) => ({ value: item.resource_id, label: `${item.host_name} / ${item.name}` }))} />
        </Form.Item>
        <Form.Item label="Volume 名称" name="name" rules={[{ required: true, max: 255 }]}><Input className="nx-technical-input" placeholder="data.qcow2" /></Form.Item>
        <Form.Item label="格式" name="volume_format"><Select options={[{ value: "qcow2", label: "qcow2" }, { value: "raw", label: "raw" }]} /></Form.Item>
        <Form.Item label="容量（GiB）" name="capacity_gib" rules={[{ required: true }]}><InputNumber min={1} max={8 * 1024 * 1024} /></Form.Item>
      </div>
      <div className="nx-form-actions nx-form-actions-end"><Button type="primary" htmlType="submit" loading={loading}>检查创建配置</Button></div>
    </Form>
  );
}

function splitOptions(value: unknown): string[] {
  return typeof value === "string" ? value.split(",").map((item) => item.trim()).filter(Boolean) : [];
}
