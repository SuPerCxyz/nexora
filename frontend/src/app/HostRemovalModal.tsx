import { Alert, Button, Input, Modal, Radio, Space } from "antd";
import { useEffect, useState } from "react";

import type { HostRemovalPreview } from "../api/hostRemoval";
import { applyHostRemoval, previewHostRemoval } from "../api/hostRemoval";

export function HostRemovalModal({ hostId, hostName, open, onClose }: { hostId: string; hostName: string; open: boolean; onClose: () => void }) {
  const [mode, setMode] = useState("local_only");
  const [preview, setPreview] = useState<HostRemovalPreview | null>(null);
  const [confirmationName, setConfirmationName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!open) { setMode("local_only"); setPreview(null); setConfirmationName(""); setError(null); } }, [open]);
  async function buildPreview() {
    setLoading(true); setError(null);
    try { setPreview(await previewHostRemoval(hostId, mode)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "移除预检失败"); }
    finally { setLoading(false); }
  }
  async function apply() {
    if (!preview) return;
    setLoading(true);
    try { window.location.assign((await applyHostRemoval(preview, confirmationName)).location); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "节点移除提交失败"); setLoading(false); }
  }
  return <Modal title={`移除节点 ${hostName}`} open={open} onCancel={onClose} footer={null} destroyOnHidden>
    <Space orientation="vertical" size={12} className="nx-page-stack">
      <Alert type="warning" showIcon={false} message="只移除 Nexora 管理关系，不删除虚拟机、磁盘、Pool、网络、Bridge、VLAN、IP 或路由。" />
      {!preview ? <>
        <Radio.Group value={mode} onChange={(event) => setMode(event.target.value)} className="nx-removal-options">
          <Radio value="local_only"><strong>仅从 Nexora 移除</strong><span>不连接或修改远端节点</span></Radio>
          <Radio value="clean_temporary"><strong>移除并清理临时管理信息</strong><span>只清理预览列出的 Nexora 临时路径与 transient unit</span></Radio>
        </Radio.Group>
        <Button className="nx-btn-danger" loading={loading} onClick={buildPreview}>生成移除预览</Button>
      </> : <>
        <div><strong>模式</strong><span className="nx-technical">{preview.mode}</span></div>
        <Inventory label="临时路径" values={preview.paths} />
        <Inventory label="Transient units" values={preview.units} />
        {preview.warnings.map((warning) => <Alert key={warning} type="warning" showIcon={false} message={warning} />)}
        <Alert type="error" showIcon={false} message="确认后将删除本地凭据、Host Key 和资源缓存，远端业务资源始终保留。" />
        <label htmlFor="host-removal-confirmation">输入节点名称 {hostName} 以确认</label>
        <Input id="host-removal-confirmation" value={confirmationName} onChange={(event) => setConfirmationName(event.target.value)} autoComplete="off" />
        <Space><Button onClick={() => setPreview(null)}>返回修改</Button><Button className="nx-btn-danger" disabled={confirmationName !== hostName} loading={loading} onClick={apply}>确认移除节点</Button></Space>
      </>}
      {error && <Alert type="error" showIcon={false} message={error} />}
    </Space>
  </Modal>;
}

function Inventory({ label, values }: { label: string; values: string[] }) {
  return <div><strong>{label} · {values.length}</strong>{values.map((value) => <code className="nx-technical" key={value}>{value}</code>)}</div>;
}
