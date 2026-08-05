import { Alert, Button, Form, Input, Modal, Space, Table, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";

import type { VmSnapshotSummary } from "../api/contracts";
import {
  applySnapshot,
  previewSnapshot,
  type SnapshotOperation,
  type SnapshotPreview,
} from "../api/vmSnapshots";
import { PageEmpty } from "./PageState";
import { StatusTag } from "./StatusTag";
import { formatDateTime } from "./dateTime";

type Props = {
  hostId: string;
  vmId: string;
  vmName: string;
  snapshots: VmSnapshotSummary[];
};

type Target = {
  operation: SnapshotOperation;
  snapshot?: VmSnapshotSummary;
};

export function VmSnapshots({ hostId, vmId, vmName, snapshots }: Props) {
  const [target, setTarget] = useState<Target | null>(null);
  const [preview, setPreview] = useState<SnapshotPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [form] = Form.useForm();

  const open = (operation: SnapshotOperation, snapshot?: VmSnapshotSummary) => {
    setPreview(null);
    form.resetFields();
    if (snapshot) form.setFieldsValue({ name: snapshot.name });
    setTarget({ operation, snapshot });
  };
  const createPreview = async (values: { name: string; description?: string }) => {
    if (!target) return;
    setBusy(true);
    try {
      setPreview(await previewSnapshot(hostId, vmId, {
        operation: target.operation,
        name: values.name,
        description: values.description,
        snapshot_resource_id: target.snapshot?.resource_id,
      }));
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "快照预检失败");
    } finally {
      setBusy(false);
    }
  };
  const apply = async () => {
    if (!preview) return;
    setBusy(true);
    try {
      const confirmation = preview.operation === "revert" ? vmName : undefined;
      window.location.assign(await applySnapshot(hostId, vmId, preview, confirmation));
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "创建快照任务失败");
      setBusy(false);
    }
  };

  const columns: ColumnsType<VmSnapshotSummary> = [
    { title: "名称", dataIndex: "name", render: (name: string) => <strong>{name}</strong> },
    { title: "状态", dataIndex: "state", render: snapshotState },
    { title: "创建时间", dataIndex: "creation_time", responsive: ["md"], render: (value) => formatDateTime(value) },
    { title: "当前", dataIndex: "current", width: 80, render: (value: boolean) => <StatusTag label={value ? "当前" : "历史"} tone={value ? "running" : "unknown"} /> },
    { title: "操作", width: 176, render: (_, item) => <Space size={8}><Button size="small" className="nx-btn-warning" onClick={() => open("revert", item)}>恢复</Button><Button size="small" className="nx-btn-danger" onClick={() => open("delete", item)}>删除</Button></Space> },
  ];

  return <>
    <Space orientation="vertical" size={12} className="nx-page-stack">
      <Button className="nx-btn-primary" onClick={() => open("create")}>创建快照</Button>
      <Table rowKey="resource_id" columns={columns} dataSource={snapshots} pagination={false} locale={{ emptyText: <PageEmpty description="暂无快照" /> }} />
    </Space>
    <Modal title={title(target?.operation)} open={target !== null} onCancel={() => setTarget(null)} footer={null} width={720}>
      {!preview ? <Form form={form} layout="vertical" onFinish={createPreview}>
        <Form.Item name="name" label="快照名称" rules={[{ required: true }]}><Input disabled={target?.operation !== "create"} maxLength={128} /></Form.Item>
        {target?.operation === "create" && <Form.Item name="description" label="说明"><Input.TextArea maxLength={512} /></Form.Item>}
        {target?.operation === "revert" && <Alert type="warning" showIcon message="恢复会将虚拟机回退到所选快照状态" />}
        <Button htmlType="submit" className="nx-btn-primary" loading={busy}>生成变更预览</Button>
      </Form> : <Space orientation="vertical" size={12} className="nx-page-stack">
        <Alert type={preview.operation === "delete" ? "warning" : "info"} showIcon message="执行前仍会重新校验虚拟机和快照版本" />
        <pre className="nx-code nx-code-light"><code>{preview.diffText}</code></pre>
        <Space><Button onClick={() => setPreview(null)}>返回</Button><Button className={preview.operation === "delete" ? "nx-btn-danger" : "nx-btn-primary"} loading={busy} onClick={apply}>确认并创建任务</Button></Space>
      </Space>}
    </Modal>
  </>;
}

function title(operation?: SnapshotOperation) {
  return {
    create: "创建快照",
    delete: "删除快照",
    revert: "恢复快照",
  }[operation ?? "create"];
}

function snapshotState(state: string) {
  const labels: Record<string, string> = {
    running: "运行时快照",
    paused: "暂停时快照",
    shutoff: "关机快照",
    disk_snapshot: "磁盘快照",
  };
  const tone = state === "running" ? "running" : state === "paused" ? "paused" : "stopped";
  return <StatusTag label={labels[state] ?? "状态未知"} tone={tone} />;
}
