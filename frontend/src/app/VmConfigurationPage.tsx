import { Alert, Button, Card, Collapse, Flex, Form, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { loadVmConfiguration, loadVmHistory, rollbackVmConfiguration, saveVmConfiguration } from "../api/vmConfiguration";
import type { VmConfiguration, VmXmlHistoryItem } from "../api/vmConfiguration";
import { formatDateTime } from "./dateTime";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { VmStatusTag } from "./StatusTag";
import { AdvancedConfiguration, NetworkConfiguration, PeripheralConfiguration, StorageConfiguration } from "./VmConfigurationSections";

export function VmConfigurationPage({ hostId, vmId }: { hostId: string; vmId: string }) {
  const [data, setData] = useState<VmConfiguration | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<VmXmlHistoryItem[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [rollbacking, setRollbacking] = useState(false);

  useEffect(() => { loadVmConfiguration(hostId, vmId).then(setData).catch(setError); }, [hostId, vmId]);
  if (error) return <PageError error={error} />;
  if (!data) return <PageLoading />;

  const saveChange = async (operation: string, values: Record<string, unknown>) => {
    try { window.location.assign((await saveVmConfiguration(data, operation, values)).location); }
    catch (caught) { message.error(caught instanceof Error ? caught.message : "配置保存失败"); }
  };
  async function openHistory() {
    setHistoryOpen(true);
    setHistoryError(null);
    setHistory(null);
    try { setHistory((await loadVmHistory(hostId, vmId)).items); }
    catch (caught) { setHistoryError(caught instanceof Error ? caught.message : "配置历史读取失败"); }
  }
  async function doRollback(item: VmXmlHistoryItem) {
    setRollbacking(true);
    try { window.location.assign((await rollbackVmConfiguration(hostId, vmId, item.id)).location); }
    catch (caught) { message.error(caught instanceof Error ? caught.message : "回滚失败"); setRollbacking(false); }
  }
  const prefix = `/hosts/${hostId}/vms/${vmId}`;

  return <Space orientation="vertical" size={12} className="nx-page-stack">
    <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap>
      <div><Flex align="center" gap={12} wrap><Typography.Title level={2}>{data.vm.name} · 配置</Typography.Title><VmStatusTag state={data.vm.state} /></Flex><Typography.Text type="secondary">修改后直接保存进入任务队列；每次保存前自动记录前一版 XML，可随时回滚</Typography.Text></div>
      <Space wrap><Button className="nx-btn-info" onClick={openHistory}>历史版本</Button><Button href={prefix} className="nx-btn-info">返回详情</Button></Space>
    </Flex>
    {!data.vm.persistent && <Alert type="warning" showIcon message="临时虚拟机不支持持久化配置修改" />}
    {data.vm.active && <Alert type="info" showIcon message="虚拟机正在运行：CPU / 内存 / 高级配置的修改会写入持久化配置，需重启虚拟机后生效（保存后显示待重启标记）；磁盘、网卡与光驱热插拔会在运行中即时生效。" />}
    <Collapse defaultActiveKey={["compute", "storage"]} items={[
      { key: "compute", label: "计算与内存", children: <ComputeForms data={data} preview={saveChange} /> },
      { key: "storage", label: "磁盘与光驱", children: <StorageConfiguration data={data} preview={saveChange} /> },
      { key: "network", label: "网络接口", children: <NetworkConfiguration data={data} preview={saveChange} /> },
      { key: "peripheral", label: "直通设备与共享目录", children: <PeripheralConfiguration data={data} preview={saveChange} /> },
      { key: "advanced", label: "高级配置", children: <AdvancedConfiguration data={data} preview={saveChange} /> },
    ]} />
    <Modal title="配置历史版本" open={historyOpen} onCancel={() => setHistoryOpen(false)} footer={null} width={600}>
      {historyError ? <Alert type="error" showIcon message={historyError} /> : history === null ? <PageLoading /> : history.length === 0 ? <PageEmpty description="尚无配置历史快照；保存配置时会自动记录前一个版本" /> : (
        <Table rowKey="id" dataSource={history} pagination={false} columns={[
          { title: "保存时间", dataIndex: "created_at", render: (value: string) => formatDateTime(value, { dateStyle: "short", timeStyle: "medium" }) },
          { title: "XML 摘要", dataIndex: "xml_hash", render: (value: string) => <code className="nx-technical">{value.slice(0, 16)}…</code> },
          { title: "操作", width: 160, render: (_, item) => (
            <Popconfirm title="回滚到此版本？" description="将用该历史 XML 恢复虚拟机持久配置（执行前仍校验资源版本）" okText="确认回滚" cancelText="取消" onConfirm={() => doRollback(item)}>
              <Button size="small" className="nx-btn-danger" loading={rollbacking}>回滚到此版本</Button>
            </Popconfirm>
          ) },
        ]} />
      )}
    </Modal>
  </Space>;
}

function ComputeForms({ data, preview }: { data: VmConfiguration; preview: (operation: string, values: Record<string, unknown>) => void }) {
  const cpu = data.cpu;
  const memory = data.memory;
  const [cpuForm] = Form.useForm();
  const cpuValues = Form.useWatch([], cpuForm) ?? {};
  const topoCells = ["sockets", "dies", "clusters", "cores", "threads"];
  const topoProduct = topoCells.reduce((product, name) => product * Number(cpuValues[name] ?? 1), 1);
  const maxVcpus = Number(cpuValues.maximum_vcpus ?? 1);
  const topoExceeds = topoProduct > maxVcpus;
  return <Space orientation="vertical" size={12} className="nx-page-stack">
    <Card title="CPU 拓扑"><Form form={cpuForm} layout="vertical" initialValues={cpu ?? {}} onFinish={(values) => preview("cpu", values)}><div className="nx-form-grid-4">{[
      ["current_vcpus", "当前 vCPU"], ["maximum_vcpus", "最大 vCPU"], ["sockets", "Sockets"], ["dies", "Dies"], ["clusters", "Clusters"], ["cores", "Cores"], ["threads", "Threads"],
    ].map(([name, label]) => <Form.Item key={name} name={name} label={label} rules={[{ required: true }]}><InputNumber min={1} max={1024} /></Form.Item>)}</div>
      {topoExceeds && <Alert type="warning" showIcon message={`拓扑乘积 ${topoProduct} 超过最大 vCPU ${maxVcpus}，请减少 Sockets/Dies/Cores/Threads 或增大最大 vCPU`} />}
      {!topoExceeds && topoProduct < maxVcpus && <Alert type="info" showIcon message={`当前拓扑乘积为 ${topoProduct}，小于最大 vCPU ${maxVcpus}（预留热插拔余量合法）`} />}
      <Flex justify="flex-end" className="nx-form-actions-end"><Button htmlType="submit" className="nx-btn-primary" disabled={!cpu || !data.vm.persistent || topoExceeds}>保存 CPU</Button></Flex></Form></Card>
    <Card title="内存"><Form layout="vertical" initialValues={{ ...memory, current_mib: Number(memory?.current_kib ?? 0) / 1024, maximum_mib: Number(memory?.maximum_kib ?? 0) / 1024 }} onFinish={(values) => preview("memory", values)}><div className="nx-form-grid-4">
      <Form.Item name="current_mib" label="当前内存 MiB" rules={[{ required: true }]}><InputNumber min={1} /></Form.Item><Form.Item name="maximum_mib" label="最大内存 MiB" rules={[{ required: true }]}><InputNumber min={1} /></Form.Item>
      <Choice name="source_type" label="Source" values={["anonymous", "file", "memfd"]} /><Choice name="access_mode" label="Access" values={["shared", "private"]} /><Choice name="allocation_mode" label="Allocation" values={["immediate", "ondemand"]} />
    </div><Flex gap={24} wrap><Toggle name="hugepages" label="HugePages" /><Toggle name="locked" label="Locked memory" /><Toggle name="discard" label="Discard" /></Flex><Flex justify="flex-end" className="nx-form-actions-end"><Button htmlType="submit" className="nx-btn-primary" disabled={!memory || !data.vm.persistent}>保存内存</Button></Flex></Form></Card>
  </Space>;
}

function Choice({ name, label, values }: { name: string; label: string; values: string[] }) { return <Form.Item name={name} label={label}><Select allowClear options={values.map((value) => ({ value, label: value }))} /></Form.Item>; }
function Toggle({ name, label }: { name: string; label: string }) { return <Form.Item name={name} label={label} valuePropName="checked"><Switch /></Form.Item>; }
