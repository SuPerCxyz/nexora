import { Alert, Button, Form, Input, InputNumber, Modal, Space } from "antd";
import { useEffect, useState } from "react";

import type { NetworkPreview } from "../api/network";
import { applyNetwork, previewBridge, previewVlan } from "../api/network";
import { navigateToTask } from "./navigateToTask";

export function NetworkChangeModal({
  hostId,
  kind,
  open,
  onClose,
}: {
  hostId: string;
  kind: "bridge" | "vlan";
  open: boolean;
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  const [preview, setPreview] = useState<NetworkPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!open) { form.resetFields(); setPreview(null); setError(null); } }, [form, open]);

  async function buildPreview() {
    setLoading(true);
    setError(null);
    try {
      const values = await form.validateFields();
      const request = { ...values, host_id: hostId };
      setPreview(kind === "bridge" ? await previewBridge(request) : await previewVlan(request));
    } catch (caught) {
      if (caught instanceof Error) setError(caught.message);
    } finally { setLoading(false); }
  }

  async function apply() {
    if (!preview) return;
    setLoading(true);
    try { navigateToTask((await applyNetwork(preview)).location); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "网络变更提交失败"); setLoading(false); }
  }

  return <Modal title={kind === "bridge" ? "创建 Bridge" : "创建 VLAN"} open={open} onCancel={onClose} footer={null} width={720} destroyOnHidden>
    <Space orientation="vertical" size={12} className="nx-page-stack">
      <Alert type="warning" showIcon={false} title="变更仅作用于运行态，不修改持久化配置；失败时自动执行回滚脚本。" />
      {!preview ? <Form form={form} layout="vertical" requiredMark={false}>
        {kind === "bridge" ? <>
          <Form.Item name="bridge_name" label="Bridge 名称" rules={[{ required: true }, { pattern: /^[a-zA-Z0-9._-]{1,15}$/, message: "请输入合法接口名称" }]}><Input placeholder="br1" /></Form.Item>
          <Form.Item name="attach_iface" label="附加物理口（可选）" rules={[{ pattern: /^[a-zA-Z0-9._-]{1,15}$/, message: "请输入合法接口名称" }]}><Input placeholder="enp1s0" /></Form.Item>
        </> : <>
          <Form.Item name="parent_iface" label="父接口" rules={[{ required: true }, { pattern: /^[a-zA-Z0-9._-]{1,15}$/, message: "请输入合法接口名称" }]}><Input placeholder="enp1s0" /></Form.Item>
          <Form.Item name="vlan_id" label="VLAN ID" rules={[{ required: true }]}><InputNumber min={1} max={4094} className="nx-full-width" /></Form.Item>
          <Form.Item name="vlan_name" label="VLAN 名称（可选）" rules={[{ pattern: /^[a-zA-Z0-9._-]{1,15}$/, message: "请输入合法接口名称" }]}><Input placeholder="enp1s0.100" /></Form.Item>
        </>}
        <Button type="primary" loading={loading} onClick={buildPreview}>生成安全预检</Button>
      </Form> : <>
        <div><strong>目标接口</strong><div className="nx-technical">{preview.target_iface}</div></div>
        <pre className="nx-code" aria-label="网络回滚脚本"><code>{preview.rollback_script}</code></pre>
        <Space><Button onClick={() => setPreview(null)}>返回修改</Button><Button type="primary" loading={loading} onClick={apply}>确认并执行</Button></Space>
      </>}
      {error && <Alert type="error" showIcon={false} title={error} />}
    </Space>
  </Modal>;
}
