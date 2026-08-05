import { Alert, Button, Checkbox, Form, Input, Modal, Space, message } from "antd";
import { useEffect, useState } from "react";

import type { VmDetail, VmRemovePreview } from "../api/contracts";
import { applyVmRemove, previewVmRemove } from "../api/core";

export function VmRemoveModal({ data, open, mode, onClose }: {
  data: VmDetail;
  open: boolean;
  mode: "delete" | "rename";
  onClose: () => void;
}) {
  const [preview, setPreview] = useState<VmRemovePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmationName, setConfirmationName] = useState("");
  const [removeDisks, setRemoveDisks] = useState(false);
  const [removeNvram, setRemoveNvram] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    if (!open) return;
    setPreview(null);
    setConfirmationName("");
    setRemoveDisks(false);
    setRemoveNvram(false);
    form.resetFields();
  }, [form, mode, open]);

  const title = mode === "delete" ? "删除虚拟机" : "重命名虚拟机";

  const generate = async (values: { target_name?: string }) => {
    setBusy(true);
    try {
      setPreview(await previewVmRemove(data.vm.host_id, data.vm.native_id, {
        operation: mode,
        target_name: values.target_name,
        remove_disks: removeDisks,
        remove_nvram: removeNvram,
      }));
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : `${title}预检失败`);
    } finally {
      setBusy(false);
    }
  };
  const apply = async () => {
    if (!preview) return;
    setBusy(true);
    try {
      const task = await applyVmRemove(
        data.vm.host_id, data.vm.native_id, preview, confirmationName,
      );
      window.location.assign(task.location);
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : `创建${title}任务失败`);
      setBusy(false);
    }
  };

  return <Modal title={title} open={open} onCancel={onClose} footer={null} width={720}>
    {!preview ? <Form form={form} layout="vertical" onFinish={generate}>
      <Alert type="warning" showIcon message="虚拟机必须已关机。删除操作默认仅移除虚拟机定义，保留磁盘。"/>
      {mode === "rename" ? (
        <Form.Item name="target_name" label="新虚拟机名称" rules={[{ required: true }]}><Input maxLength={128} placeholder={data.vm.name} /></Form.Item>
      ) : (
        <Space direction="vertical" className="nx-page-stack">
          <Checkbox checked={removeDisks} onChange={(event) => setRemoveDisks(event.target.checked)}>同时删除磁盘文件</Checkbox>
          <Checkbox checked={removeNvram} onChange={(event) => setRemoveNvram(event.target.checked)}>同时删除 NVRAM（UEFI）</Checkbox>
        </Space>
      )}
      <Button htmlType="submit" className="nx-btn-danger" loading={busy}>{mode === "delete" ? "生成删除预览" : "生成重命名预览"}</Button>
    </Form> : <Space orientation="vertical" size={12} className="nx-page-stack">
      <pre className="nx-code nx-code-light"><code>{preview.diff_text}</code></pre>
      <Alert type="error" showIcon message={`输入虚拟机名称 ${data.vm.name} 以确认`} />
      <Input value={confirmationName} onChange={(event) => setConfirmationName(event.target.value)} autoComplete="off" placeholder="虚拟机名称" />
      <Space>
        <Button onClick={() => setPreview(null)}>返回</Button>
        <Button className="nx-btn-danger" loading={busy} disabled={confirmationName !== data.vm.name} onClick={apply}>确认并创建任务</Button>
      </Space>
    </Space>}
  </Modal>;
}
