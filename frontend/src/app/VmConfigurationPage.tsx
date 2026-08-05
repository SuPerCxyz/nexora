import { Alert, Button, Card, Collapse, Flex, Form, InputNumber, Modal, Select, Space, Switch, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { applyVmConfiguration, loadVmConfiguration, previewVmConfiguration } from "../api/vmConfiguration";
import type { ChangePreview, VmConfiguration } from "../api/vmConfiguration";
import { PageError, PageLoading } from "./PageState";
import { VmStatusTag } from "./StatusTag";
import { AdvancedConfiguration, NetworkConfiguration, PeripheralConfiguration, StorageConfiguration } from "./VmConfigurationSections";

export function VmConfigurationPage({ hostId, vmId }: { hostId: string; vmId: string }) {
  const [data, setData] = useState<VmConfiguration | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [preview, setPreview] = useState<ChangePreview | null>(null);
  const [applying, setApplying] = useState(false);

  useEffect(() => { loadVmConfiguration(hostId, vmId).then(setData).catch(setError); }, [hostId, vmId]);
  if (error) return <PageError error={error} />;
  if (!data) return <PageLoading />;

  const previewChange = async (path: string, values: Record<string, unknown>) => {
    try { setPreview(await previewVmConfiguration(path, data, values)); }
    catch (caught) { message.error(caught instanceof Error ? caught.message : "配置预检失败"); }
  };
  const apply = async () => {
    if (!preview) return;
    setApplying(true);
    try { window.location.assign(await applyVmConfiguration(data, preview)); }
    catch (caught) { message.error(caught instanceof Error ? caught.message : "创建任务失败"); setApplying(false); }
  };
  const prefix = `/hosts/${hostId}/vms/${vmId}`;

  return <Space orientation="vertical" size={20} className="nx-page-stack">
    <Flex className="nx-detail-header" justify="space-between" align="center" gap={16} wrap>
      <div><Flex align="center" gap={12} wrap><Typography.Title level={2}>{data.vm.name} · 配置</Typography.Title><VmStatusTag state={data.vm.state} /></Flex><Typography.Text type="secondary">配置修改会先生成 XML Diff，确认后进入任务队列</Typography.Text></div>
      <Button href={prefix} className="nx-btn-info">返回详情</Button>
    </Flex>
    {!data.vm.persistent && <Alert type="warning" showIcon message="临时虚拟机不支持持久化配置修改" />}
    <Collapse defaultActiveKey={["compute", "storage"]} items={[
      { key: "compute", label: "计算与内存", children: <ComputeForms data={data} preview={previewChange} /> },
      { key: "storage", label: "磁盘与光驱", children: <StorageConfiguration data={data} preview={previewChange} /> },
      { key: "network", label: "网络接口", children: <NetworkConfiguration data={data} preview={previewChange} /> },
      { key: "peripheral", label: "直通设备与共享目录", children: <PeripheralConfiguration data={data} preview={previewChange} /> },
      { key: "advanced", label: "高级配置", children: <AdvancedConfiguration data={data} preview={previewChange} /> },
    ]} />
    <Modal title="确认配置变更" open={preview !== null} width={760} onCancel={() => setPreview(null)} footer={<Space><Button onClick={() => setPreview(null)}>取消</Button><Button className="nx-btn-primary" loading={applying} onClick={apply}>确认并创建任务</Button></Space>}>
      <Alert type="info" showIcon message="请确认以下 Domain XML Diff；执行前仍会重新校验资源版本。" />
      <pre className="nx-code nx-code-light"><code>{preview?.diff}</code></pre>
    </Modal>
  </Space>;
}

function ComputeForms({ data, preview }: { data: VmConfiguration; preview: (operation: string, values: Record<string, unknown>) => void }) {
  const cpu = data.cpu;
  const memory = data.memory;
  return <Space orientation="vertical" size={16} className="nx-page-stack">
    <Card title="CPU 拓扑"><Form layout="vertical" initialValues={cpu ?? {}} onFinish={(values) => preview("cpu", values)}><div className="nx-form-grid">{[
      ["current_vcpus", "当前 vCPU"], ["maximum_vcpus", "最大 vCPU"], ["sockets", "Sockets"], ["dies", "Dies"], ["clusters", "Clusters"], ["cores", "Cores"], ["threads", "Threads"],
    ].map(([name, label]) => <Form.Item key={name} name={name} label={label} rules={[{ required: true }]}><InputNumber min={1} max={65536} /></Form.Item>)}</div><Button htmlType="submit" className="nx-btn-primary" disabled={!cpu || !data.vm.persistent}>预览 CPU Diff</Button></Form></Card>
    <Card title="内存"><Form layout="vertical" initialValues={{ ...memory, current_mib: Number(memory?.current_kib ?? 0) / 1024, maximum_mib: Number(memory?.maximum_kib ?? 0) / 1024 }} onFinish={(values) => preview("memory", values)}><div className="nx-form-grid">
      <Form.Item name="current_mib" label="当前内存 MiB" rules={[{ required: true }]}><InputNumber min={1} /></Form.Item><Form.Item name="maximum_mib" label="最大内存 MiB" rules={[{ required: true }]}><InputNumber min={1} /></Form.Item>
      <Choice name="source_type" label="Source" values={["anonymous", "file", "memfd"]} /><Choice name="access_mode" label="Access" values={["shared", "private"]} /><Choice name="allocation_mode" label="Allocation" values={["immediate", "ondemand"]} />
    </div><Flex gap={20} wrap><Toggle name="hugepages" label="HugePages" /><Toggle name="locked" label="Locked memory" /><Toggle name="discard" label="Discard" /></Flex><Button htmlType="submit" className="nx-btn-primary" disabled={!memory || !data.vm.persistent}>预览内存 Diff</Button></Form></Card>
  </Space>;
}

function Choice({ name, label, values }: { name: string; label: string; values: string[] }) { return <Form.Item name={name} label={label}><Select allowClear options={values.map((value) => ({ value, label: value }))} /></Form.Item>; }
function Toggle({ name, label }: { name: string; label: string }) { return <Form.Item name={name} label={label} valuePropName="checked"><Switch /></Form.Item>; }
