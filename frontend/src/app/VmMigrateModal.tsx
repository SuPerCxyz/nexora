import { Alert, Button, Form, Modal, Select, Space, message } from "antd";
import { useEffect, useState } from "react";

import type { VmDetail } from "../api/contracts";
import { loadStorage } from "../api/storage";
import { applyVmMigrate, previewVmMigrate, type VmMigratePreview } from "../api/vmClone";

export function VmMigrateModal({ data, open, onClose }: {
  data: VmDetail;
  open: boolean;
  onClose: () => void;
}) {
  const [pools, setPools] = useState<Array<{ value: string; label: string }>>([]);
  const [preview, setPreview] = useState<VmMigratePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    if (!open) return;
    setPreview(null);
    form.resetFields();
    loadStorage().then((storage) => setPools(storage.pools
      .filter((pool) => pool.writable && pool.active)
      .map((pool) => ({
        value: pool.resource_id,
        label: `${pool.host_name} · ${pool.name} · ${pool.pool_type}`,
      })))).catch((caught) => message.error(caught instanceof Error ? caught.message : "读取存储池失败"));
  }, [form, open]);

  const generate = async (values: { target_pool_id: string }) => {
    setBusy(true);
    try {
      setPreview(await previewVmMigrate(
        data.vm.host_id, data.vm.native_id, values.target_pool_id,
      ));
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "迁移预检失败");
    } finally {
      setBusy(false);
    }
  };
  const apply = async () => {
    if (!preview) return;
    setBusy(true);
    try {
      const task = await applyVmMigrate(data.vm.host_id, data.vm.native_id, preview);
      window.location.assign(task.location);
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "创建迁移任务失败");
      setBusy(false);
    }
  };

  return <Modal title="关机迁移" open={open} onCancel={onClose} footer={null} width={760}>
    {!preview ? <Form form={form} layout="vertical" onFinish={generate}>
      <Alert type="info" showIcon message="目标节点由所选存储池明确决定；源虚拟机必须已关机。迁移保留 UUID 与 MAC，成功后默认不启动目标虚拟机。" />
      <Form.Item name="target_pool_id" label="目标节点与存储池" rules={[{ required: true }]}><Select options={pools} /></Form.Item>
      <Button htmlType="submit" className="nx-btn-primary" loading={busy}>生成迁移预览</Button>
    </Form> : <Space orientation="vertical" size={12} className="nx-page-stack">
      <Alert type="info" showIcon message={`将复制 ${preview.file_count} 个磁盘或固件文件，保留源虚拟机与磁盘（源端清理需另行确认）`} />
      <pre className="nx-code nx-code-light"><code>{preview.diff_text}</code></pre>
      <Space><Button onClick={() => setPreview(null)}>返回</Button><Button className="nx-btn-primary" loading={busy} onClick={apply}>确认并创建任务</Button></Space>
    </Space>}
  </Modal>;
}
