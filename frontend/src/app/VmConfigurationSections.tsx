import { Button, Card, Flex, Form, Input, InputNumber, Select, Space, Switch, Table, Typography } from "antd";

import type { VmConfiguration } from "../api/vmConfiguration";
import { StatusTag } from "./StatusTag";

type Preview = (operation: string, values: Record<string, unknown>) => void;
type Props = { data: VmConfiguration; preview: Preview };
type ConfigDisk = {
  key: string;
  target?: unknown;
  device?: unknown;
  source?: unknown;
  bus?: unknown;
};
type ConfigInterface = {
  key: string;
  type?: string;
  source?: string | null;
  mac?: string | null;
  model?: string | null;
};

export function NetworkConfiguration({ data, preview }: Props) {
  const interfaces: ConfigInterface[] = data.interfaces.map((item, index) => ({
    ...item,
    key: `${item.mac ?? index}`,
  }));
  const networkOptions = data.networks.map((item) => ({
    value: `${item.kind}:${item.name}`,
    label: `${item.kind === "bridge" ? "Bridge" : "libvirt Network"} / ${item.name}`,
  }));
  return <Space orientation="vertical" size={16} className="nx-page-stack">
    <Card title="当前网络接口"><Table dataSource={interfaces} pagination={false} tableLayout="fixed" columns={[
      { title: "类型", dataIndex: "type" }, { title: "Source", dataIndex: "source", responsive: ["md"] },
      { title: "MAC", dataIndex: "mac", responsive: ["md"] }, { title: "Model", dataIndex: "model" },
      { title: "操作", width: 160, render: (_, item) => <Flex gap={8}>
        <Button size="small" className="nx-btn-info" onClick={() => preview("interface_update", { mac: item.mac, model: item.model, new_mac: item.mac, live: data.vm.active })}>更新</Button>
        <Button size="small" className="nx-btn-danger" onClick={() => preview("interface_detach", { mac: item.mac, live: data.vm.active })}>移除</Button>
      </Flex> },
    ]} /></Card>
    <Card title="添加网络接口"><Form layout="vertical" onFinish={(values) => preview("interface_attach", { kind: String(values.network).split(":")[0], source: String(values.network).split(":").slice(1).join(":"), model: values.model, mac: values.mac || undefined, live: data.vm.active })}><div className="nx-form-grid">
      <Form.Item name="network" label="目标网络" rules={[{ required: true }]}><Select options={networkOptions} placeholder="选择 Bridge 或 libvirt Network" /></Form.Item>
      <Form.Item name="model" label="型号" initialValue="virtio"><Select options={[{ value: "virtio", label: "VirtIO" }, { value: "e1000e", label: "e1000e" }, { value: "e1000", label: "e1000" }, { value: "rtl8139", label: "rtl8139" }]} /></Form.Item>
      <Form.Item name="mac" label="MAC（可选）"><Input placeholder="自动生成" /></Form.Item>
    </div><Button htmlType="submit" className="nx-btn-primary" disabled={!data.networks.length}>预览添加网卡 Diff</Button></Form></Card>
  </Space>;
}

export function StorageConfiguration({ data, preview }: Props) {
  const disks: ConfigDisk[] = data.disks.map((item, index) => ({
    ...item,
    key: `${item.target ?? index}`,
  }));
  const isIso = (path: string | null) => path?.toLowerCase().endsWith(".iso") ?? false;
  const volumes = data.storage_volumes.filter((item) => (item.format === "qcow2" || item.format === "raw") && !isIso(item.path));
  const localIsos = data.storage_volumes.filter((item) => isIso(item.path));
  const cdroms = disks.filter((item) => item.device === "cdrom");
  return <Space orientation="vertical" size={16} className="nx-page-stack">
    <Card title="当前磁盘与光驱"><Table dataSource={disks} pagination={false} tableLayout="fixed" columns={[
      { title: "Target", dataIndex: "target" }, { title: "设备", dataIndex: "device" },
      { title: "Source", dataIndex: "source", responsive: ["md"] },
      { title: "操作", width: 96, render: (_, disk) => disk.device === "disk" ? <Button size="small" className="nx-btn-danger" onClick={() => preview("disk_detach", { target: disk.target, bus: disk.bus, device: disk.device, source: disk.source, live: data.vm.active })}>移除</Button> : disk.source ? <Button size="small" className="nx-btn-warning" onClick={() => preview("cdrom_eject", { target: disk.target, bus: disk.bus, expected_source: disk.source })}>弹出</Button> : "空托盘" },
    ]} /></Card>
    <Card title="挂载同节点存储卷"><Table rowKey="resource_id" dataSource={volumes} pagination={false} tableLayout="fixed" columns={[
      { title: "名称", dataIndex: "name" }, { title: "Pool", dataIndex: "pool_name" }, { title: "格式", dataIndex: "format" },
      { title: "操作", width: 96, render: (_, volume) => <Button size="small" className="nx-btn-positive" disabled={!volume.persistent_hash} onClick={() => preview("disk_attach", { volume_resource_id: volume.resource_id, bus: "virtio", live: data.vm.active })}>挂载</Button> },
    ]} /></Card>
    <Card title="挂载 ISO 到现有光驱">{cdroms.length ? cdroms.map((cdrom) => <div className="nx-config-media-row" key={String(cdrom.key)}><strong>{String(cdrom.target ?? "光驱")} · {String(cdrom.bus ?? "—")}</strong><Flex gap={8} wrap>{localIsos.map((iso) => <Button key={iso.resource_id} size="small" className="nx-btn-positive" disabled={!iso.persistent_hash} onClick={() => preview("cdrom_mount", { target: cdrom.target, bus: cdrom.bus, expected_source: cdrom.source, volume_resource_id: iso.resource_id })}>{iso.name}</Button>)}{data.platform_isos.map((iso) => <Button key={iso.id} size="small" className="nx-btn-info" onClick={() => preview(data.platform_iso_enabled ? "platform_iso_mount" : "cached_iso_mount", { target: cdrom.target, bus: cdrom.bus, expected_source: cdrom.source, media_item_id: iso.id })}>{iso.name}</Button>)}</Flex></div>) : <Typography.Text type="secondary">未发现可安全修改的 persistent CD-ROM</Typography.Text>}</Card>
  </Space>;
}

export function PeripheralConfiguration({ data, preview }: Props) {
  return <Space orientation="vertical" size={16} className="nx-page-stack">
    <Card title="PCI / USB 直通"><Form layout="vertical" onFinish={(values) => preview("host_device", values)}><div className="nx-form-grid"><Form.Item name="device_resource_id" label="节点设备" rules={[{ required: true }]}><Select options={data.host_devices.map((item) => ({ value: item.resource_id, label: `${item.name} · ${item.address}` }))} /></Form.Item><Form.Item name="action" label="操作" initialValue="attach"><Select options={[{ value: "attach", label: "挂载" }, { value: "detach", label: "卸载" }]} /></Form.Item></div><Button htmlType="submit" className="nx-btn-primary" disabled={data.vm.active || !data.host_devices.length}>预览设备 Diff</Button></Form></Card>
    <Card title="共享目录"><Form layout="vertical" onFinish={(values) => preview("shared_directory", values)}><div className="nx-form-grid"><Form.Item name="root_index" label="授权目录" rules={[{ required: true }]}><Select options={data.shared_directory_roots.map((root, index) => ({ value: index, label: root }))} /></Form.Item><Form.Item name="target_tag" label="Guest tag" rules={[{ required: true }]}><Input maxLength={36} /></Form.Item><Form.Item name="driver" label="驱动" initialValue="virtiofs"><Select options={[{ value: "virtiofs" }, { value: "9p" }]} /></Form.Item><Form.Item name="action" label="操作" initialValue="attach"><Select options={[{ value: "attach", label: "挂载" }, { value: "detach", label: "卸载" }]} /></Form.Item></div><Flex gap={16} align="center"><Form.Item name="readonly" label="只读" valuePropName="checked"><Switch /></Form.Item><Button htmlType="submit" className="nx-btn-primary" disabled={data.vm.active || !data.shared_directory_roots.length}>预览目录 Diff</Button></Flex></Form></Card>
  </Space>;
}

export function AdvancedConfiguration({ data, preview }: Props) {
  return <Space orientation="vertical" size={16} className="nx-page-stack">
    <Card title="Watchdog、vsock 与 CPU 高级参数"><Form layout="vertical" onFinish={(values) => preview("advanced_devices", values)}><div className="nx-form-grid"><Form.Item name="watchdog_enabled" label="启用 Watchdog" valuePropName="checked"><Switch /></Form.Item><Field name="watchdog_model" label="Watchdog model" values={["i6300esb", "ib700"]} initial="i6300esb" /><Field name="watchdog_action" label="Watchdog action" values={["reset", "shutdown", "poweroff", "pause", "none"]} initial="reset" /><Field name="vsock_mode" label="vsock" values={["remove", "auto", "explicit"]} initial="remove" /><Form.Item name="vsock_cid" label="vsock CID"><Input /></Form.Item><Field name="cache_mode" label="CPU cache mode" values={["emulate", "passthrough", "disable"]} /><Field name="maxphysaddr_mode" label="maxphysaddr mode" values={["emulate", "passthrough"]} /><Form.Item name="maxphysaddr_bits" label="maxphysaddr bits"><Input /></Form.Item></div><Button htmlType="submit" className="nx-btn-primary" disabled={!data.vm.persistent}>预览高级设备 Diff</Button></Form></Card>
    <Card title="NUMA 拓扑"><Form layout="vertical" onFinish={(values) => preview("numa", numaValues(String(values.cells ?? "")))}><Form.Item name="cells" label="NUMA 单元" tooltip="每行：vCPU 范围 | 内存 KiB | 访问模式"><Input.TextArea rows={4} placeholder={"0-3 | 4194304 | shared\n4-7 | 4194304 | shared"} /></Form.Item><Button htmlType="submit" className="nx-btn-primary" disabled={!data.vm.persistent || data.vm.active}>预览 NUMA Diff</Button></Form></Card>
    <Card title="CPU Pinning"><Form layout="vertical" onFinish={(values) => preview("cputune", pinningValues(String(values.pins ?? ""), String(values.emulator_cpuset ?? "")))}><Form.Item name="pins" label="vCPU 绑定" tooltip="每行：vCPU 编号 | 节点 CPU 范围"><Input.TextArea rows={4} placeholder={"0 | 0-1\n1 | 2-3"} /></Form.Item><Form.Item name="emulator_cpuset" label="模拟器线程 CPU 范围"><Input placeholder="例如 0-3" /></Form.Item><Button htmlType="submit" className="nx-btn-primary" disabled={!data.vm.persistent || data.vm.active}>预览 CPU Pinning Diff</Button></Form></Card>
    <Card title="当前高级配置"><Typography.Paragraph type="secondary">以下内容来自安全解析后的 Domain XML。</Typography.Paragraph>{data.advanced ? <pre className="nx-code nx-code-light"><code>{JSON.stringify(data.advanced, null, 2)}</code></pre> : <StatusTag label="未配置" tone="unknown" />}</Card>
  </Space>;
}

function Field({ name, label, values, initial }: { name: string; label: string; values: string[]; initial?: string }) { return <Form.Item name={name} label={label} initialValue={initial}><Select allowClear options={values.map((value) => ({ value, label: value }))} /></Form.Item>; }

function numaValues(text: string): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  text.split("\n").map((line) => line.trim()).filter(Boolean).forEach((line, index) => {
    const [cpus, memory, access] = line.split("|").map((item) => item.trim());
    values[`cell_${index}_id`] = index;
    values[`cell_${index}_cpus`] = cpus;
    values[`cell_${index}_memory_kib`] = memory;
    if (access) values[`cell_${index}_mem_access`] = access;
  });
  return values;
}

function pinningValues(text: string, emulator: string): Record<string, unknown> {
  const values: Record<string, unknown> = { emulator_cpuset: emulator };
  text.split("\n").map((line) => line.trim()).filter(Boolean).forEach((line, index) => {
    const [vcpu, cpuset] = line.split("|").map((item) => item.trim());
    values[`pin_${index}_vcpu`] = vcpu;
    values[`pin_${index}_cpuset`] = cpuset;
  });
  return values;
}
