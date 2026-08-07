import { Button, Card, Flex, Space, Table, Tabs, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type {
  GuestAgentSummary,
  VmDetail,
  VmDiskSummary,
  VmHostDeviceSummary,
  VmInterfaceSummary,
} from "../api/contracts";
import { loadGuestAgent, loadVmDetail } from "../api/core";
import { FactCard } from "./FactCard";
import { formatBytes } from "./format";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { StatusTag, VmStatusTag } from "./StatusTag";
import { VmActions } from "./VmActions";
import { VmSnapshots } from "./VmSnapshots";

export function VmDetailPage({ hostId, vmId }: { hostId: string; vmId: string }) {
  const [data, setData] = useState<VmDetail | null>(null);
  const [guestAgent, setGuestAgent] = useState<GuestAgentSummary | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    loadVmDetail(hostId, vmId).then(setData).catch(setError);
    loadGuestAgent(hostId, vmId).then(setGuestAgent).catch(() => setGuestAgent({
      state: "unavailable",
      channel_configured: false,
      hostname: null,
      addresses: [],
      message: "Guest Agent 状态暂不可用",
    }));
  }, [hostId, vmId]);

  if (error) return <PageError error={error} />;
  if (!data) return <PageLoading />;
  const passthroughNics = data.host_devices.filter((item) => item.category === "网卡").length;
  return (
    <Space orientation="vertical" size={12} className="nx-page-stack">
      <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap>
        <div className="nx-page-title">
          <Flex align="center" gap={12} wrap>
            <Typography.Title level={2}>{data.vm.name}</Typography.Title>
            <VmStatusTag state={data.vm.state} />
            {data.vm.needs_restart && <StatusTag label="待重启" tone="warning" description="配置已修改，重启虚拟机后生效" />}
          </Flex>
          <Typography.Text type="secondary">{data.vm.host_name} · {data.vm.native_id}</Typography.Text>
        </div>
        <Button className="nx-btn-info" href={`/hosts/${hostId}/vms/${vmId}/config`}>配置</Button>
      </Flex>
      <VmActions data={data} />
      <div className="nx-metric-grid">
        <FactCard label="处理器" value={`${data.vm.vcpus ?? "-"} / ${data.maximum_vcpus ?? "-"} vCPU`} />
        <FactCard label="内存" value={`${data.vm.memory_mib ?? "-"} MiB`} />
        <FactCard label="自动启动" value={data.autostart ? "已启用" : "未启用"} />
        <FactCard label="配置状态" value={configurationLabel(data.configuration_status)} />
      </div>
      <MetricSummary data={data} />
      <Card title="子系统状态">
        <div className="nx-resource-grid">
          <Subsystem name="计算与内存" detail={`${data.vm.vcpus ?? "—"} vCPU · ${data.vm.memory_mib ?? "—"} MiB`} ready />
          <Subsystem name="存储" detail={`${data.disks.length} 个设备`} ready={data.disks.length > 0} />
          <Subsystem
            name="网络"
            detail={networkSummary(data.interfaces.length, passthroughNics)}
            ready={data.interfaces.length + passthroughNics > 0}
          />
          <GuestSubsystem data={guestAgent} />
          <Subsystem name="快照" detail={`${data.snapshots.length} 个快照`} ready />
        </div>
      </Card>
      <Tabs items={detailTabs(data, guestAgent, hostId, vmId)} />
    </Space>
  );
}

function Subsystem({ name, detail, ready }: { name: string; detail: string; ready: boolean }) {
  return <div className="nx-resource-tile"><span>{name}</span><strong>{detail}</strong><StatusTag label={ready ? "正常" : "未配置"} tone={ready ? "running" : "unknown"} /></div>;
}

function GuestSubsystem({ data }: { data: GuestAgentSummary | null }) {
  const connected = data?.state === "connected";
  const label = connected ? "已连接" : data?.state === "stopped" ? "虚拟机已停止" : "需关注";
  const detail = data?.hostname ?? data?.message ?? "正在读取 Guest Agent 状态";
  return <div className="nx-resource-tile"><span>客户机集成</span><strong>{detail}</strong><StatusTag label={label} tone={connected ? "running" : data ? "warning" : "starting"} /></div>;
}

function MetricSummary({ data }: { data: VmDetail }) {
  const latest = data.metrics.at(-1);
  if (!latest) return <Card><PageEmpty description="等待首次虚拟机性能采样" /></Card>;
  return <div className="nx-metric-grid">
    <FactCard label="CPU 使用" value={latest.cpu_usage_percent === null ? "等待差分" : `${latest.cpu_usage_percent.toFixed(1)}%`} />
    <FactCard label="内存使用" value={formatKib(latest.memory_usage_kib)} />
    <FactCard label="磁盘累计 I/O" value={formatBytes(sum(latest.disk_read_bytes, latest.disk_write_bytes))} />
    <FactCard label="网络累计流量" value={formatBytes(sum(latest.net_rx_bytes, latest.net_tx_bytes))} />
  </div>;
}

function detailTabs(data: VmDetail, guestAgent: GuestAgentSummary | null, hostId: string, vmId: string) {
  return [
    {
      key: "devices",
      label: "设备",
      children: <Space orientation="vertical" size={12} className="nx-page-stack">
        <GuestAgentCard data={guestAgent} />
        <Card title="磁盘与光驱"><Table className="nx-responsive-table" rowKey={(item) => `${item.target}-${item.source}`} columns={diskColumns} dataSource={data.disks} pagination={false} tableLayout="fixed" /></Card>
        <Card title="网络接口"><Table className="nx-responsive-table" rowKey={(item) => item.mac ?? item.target ?? "interface"} columns={interfaceColumns} dataSource={data.interfaces} pagination={false} tableLayout="fixed" /></Card>
        <Card title="直通设备"><Table className="nx-responsive-table" rowKey={(item) => `${item.type}-${item.address}`} columns={hostDeviceColumns} dataSource={data.host_devices} pagination={false} tableLayout="fixed" locale={{ emptyText: "未配置 PCI/USB 直通设备" }} /></Card>
      </Space>,
    },
    {
      key: "snapshots",
      label: `快照 (${data.snapshots.length})`,
      children: <Card><VmSnapshots hostId={hostId} vmId={vmId} vmName={data.vm.name} snapshots={data.snapshots} /></Card>,
    },
    {
      key: "xml",
      label: "XML",
      children: <Card title="Persistent Domain XML"><pre className="nx-code"><code>{data.xml || "XML 不可用"}</code></pre></Card>,
    },
  ];
}

function GuestAgentCard({ data }: { data: GuestAgentSummary | null }) {
  if (!data) return <Card title="Guest Agent"><PageLoading /></Card>;
  return <Card title="Guest Agent">
    <div className="nx-guest-agent-summary">
      <StatusTag label={data.state === "connected" ? "已连接" : "未连接"} tone={data.state === "connected" ? "running" : "warning"} />
      <span>{data.hostname ?? data.message ?? "暂无客户机信息"}</span>
      {data.addresses.map((item) => <code key={`${item.interface}-${item.address}`}>{item.interface} · {item.address}/{item.prefix}</code>)}
    </div>
  </Card>;
}

const diskColumns: ColumnsType<VmDiskSummary> = [
  { title: "Target", dataIndex: "target", width: 92, render: technical },
  { title: "设备", responsive: ["md"], render: (_, item) => `${item.device ?? "未知"} · ${item.bus ?? "—"}` },
  { title: "Source", dataIndex: "source", render: technical },
  { title: "格式", dataIndex: "format", width: 88, render: (value: string | null) => <StatusTag label={value ?? "未知"} tone="unknown" /> },
  { title: "属性", responsive: ["md"], render: (_, item) => [item.readonly && "只读", item.shareable && "共享"].filter(Boolean).join(" · ") || "标准" },
];

const interfaceColumns: ColumnsType<VmInterfaceSummary> = [
  { title: "类型", dataIndex: "type", width: 88 },
  { title: "Source", dataIndex: "source", render: technical },
  { title: "MAC", dataIndex: "mac", render: technical },
  { title: "Target", dataIndex: "target", responsive: ["md"], render: technical },
  { title: "Model", dataIndex: "model", responsive: ["md"], render: technical },
];

const hostDeviceColumns: ColumnsType<VmHostDeviceSummary> = [
  { title: "设备", dataIndex: "name", render: (name: string, item) => <Space size={8} wrap><strong>{name}</strong><StatusTag label={item.category} tone="unknown" /></Space> },
  { title: "地址", dataIndex: "address", width: 150, render: technical },
  { title: "驱动", dataIndex: "driver", width: 112, responsive: ["md"], render: technical },
  { title: "IOMMU 组", dataIndex: "iommu_group", width: 104, responsive: ["md"], render: technical },
];

function technical(value: string | null) {
  return <span className="nx-technical">{value ?? "—"}</span>;
}

function configurationLabel(value: string) {
  const labels: Record<string, string> = {
    managed: "已同步",
    transient: "临时运行",
    changed_out_of_band: "发现带外变更",
    conflict: "配置冲突",
    stale: "等待刷新",
    missing: "资源缺失",
  };
  return labels[value] ?? value;
}

function networkSummary(virtualInterfaces: number, passthroughNics: number) {
  const values = [
    virtualInterfaces > 0 ? `${virtualInterfaces} 个虚拟接口` : null,
    passthroughNics > 0 ? `${passthroughNics} 个透传网卡` : null,
  ].filter(Boolean);
  return values.join(" · ") || "未配置网络设备";
}

function sum(first: number | null, second: number | null) {
  return first === null && second === null ? null : (first ?? 0) + (second ?? 0);
}

function formatKib(value: number | null) {
  return value === null ? "—" : `${(value / 1024).toFixed(0)} MiB`;
}
