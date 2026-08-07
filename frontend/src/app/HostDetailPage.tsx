import { Button, Card, Descriptions, Flex, Progress, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type {
  HostDetail,
  HostFeatureSummary,
  HostNetworkAdapterSummary,
  VmSummary,
} from "../api/contracts";
import { loadHostDetail, scanHost } from "../api/core";
import { FactCard } from "./FactCard";
import { navigateToTask } from "./navigateToTask";
import { formatBytes } from "./format";
import { formatDateTime } from "./dateTime";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { HostStatusTag, StatusTag, VmStatusTag } from "./StatusTag";
import { HostRemovalModal } from "./HostRemovalModal";

const resourceLabels: Record<string, string> = {
  virtual_machine: "虚拟机",
  snapshot: "快照",
  storage_pool: "存储池",
  storage_volume: "存储卷",
  libvirt_network: "虚拟网络",
  host_interface: "网络接口",
  pci_device: "PCI 设备",
  usb_device: "USB 设备",
};

export function HostDetailPage({ hostId }: { hostId: string }) {
  const [data, setData] = useState<HostDetail | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [removalOpen, setRemovalOpen] = useState(false);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    loadHostDetail(hostId).then(setData).catch(setError);
  }, [hostId]);

  if (error) return <PageError error={error} />;
  if (!data) return <PageLoading />;
  async function scan() {
    setScanning(true);
    try { navigateToTask((await scanHost(data!.host.id)).location); }
    catch (caught) { setError(caught instanceof Error ? caught : new Error("节点扫描提交失败")); setScanning(false); }
  }
  return (
    <Space orientation="vertical" size={12} className="nx-page-stack">
      <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap>
        <div className="nx-page-title">
          <Flex align="center" gap={12} wrap>
            <Typography.Title level={2}>{data.host.name}</Typography.Title>
            <HostStatusTag status={data.host.status} />
          </Flex>
          <Typography.Text type="secondary">
            {data.host.address} · SSH {data.host.ssh_port}
          </Typography.Text>
        </div>
        <Space wrap><Button className="nx-btn-info" loading={scanning} onClick={scan}>刷新节点信息</Button><Button className="nx-btn-danger" onClick={() => setRemovalOpen(true)}>移除节点</Button></Space>
      </Flex>
      <div className="nx-metric-grid">
        <FactCard label="登录用户" value={data.ssh_username} />
        <FactCard label="虚拟化连接" value={data.libvirt_uri} technical />
        <FactCard label="资源同步" value={formatTime(data.host.last_scanned_at)} />
        <FactCard label="节点 ID" value={data.host.id} technical />
      </div>
      <HostMetrics data={data} />
      <HardwareCard data={data} />
      <NetworkAdaptersCard adapters={data.network_adapters} />
      <FeatureSupport features={data.features} />
      <Card title="子系统状态" extra={`${resourceTotal(data)} 个资源`}>
        <div className="nx-resource-grid">
          {Object.entries(data.resource_counts).map(([type, count]) => (
            <div className="nx-resource-tile" key={type}>
              <span>{resourceLabels[type] ?? type}</span>
              <strong>{count}</strong>
              <StatusTag label="已同步" tone="running" />
            </div>
          ))}
          {Object.keys(data.resource_counts).length === 0 && <PageEmpty description="等待首次资源发现" />}
        </div>
      </Card>
      <Card title="虚拟机">
        <Table className="nx-responsive-table" rowKey="resource_id" columns={vmColumns} dataSource={data.virtual_machines} pagination={false} tableLayout="fixed" />
      </Card>
      <HostRemovalModal hostId={data.host.id} hostName={data.host.name} open={removalOpen} onClose={() => setRemovalOpen(false)} />
    </Space>
  );
}

function HardwareCard({ data }: { data: HostDetail }) {
  const hardware = data.hardware;
  const cpuTopology = [
    hardware.sockets === null ? null : `${hardware.sockets} 路`,
    hardware.cores_per_socket === null ? null : `每路 ${hardware.cores_per_socket} 核`,
    hardware.threads_per_core === null ? null : `每核 ${hardware.threads_per_core} 线程`,
    hardware.logical_cpus === null ? null : `${hardware.logical_cpus} 逻辑 CPU`,
  ].filter(Boolean).join(" · ") || "暂未获取";
  const items = [
    { key: "manufacturer", label: "设备厂商", children: hardware.manufacturer ?? "暂未获取" },
    { key: "model", label: "设备型号", children: hardware.model ?? "暂未获取" },
    { key: "os", label: "操作系统", children: hardware.os_name ?? "暂未获取" },
    { key: "kernel", label: "内核", children: hardware.kernel ?? "暂未获取" },
    { key: "architecture", label: "架构", children: hardware.architecture ?? "暂未获取" },
    { key: "memory", label: "内存", children: formatBytes(hardware.memory_bytes, { fixedUnit: "GiB" }) },
    { key: "cpu", label: "处理器", children: hardware.cpu_model ?? "暂未获取", span: 3 },
    { key: "topology", label: "CPU 拓扑", children: cpuTopology, span: 2 },
    { key: "numa", label: "NUMA", children: hardware.numa_nodes === null ? "暂未获取" : `${hardware.numa_nodes} 个节点` },
  ];
  return <Card title="硬件概览"><Descriptions items={items} column={{ xs: 1, sm: 2, lg: 3 }} /></Card>;
}

function NetworkAdaptersCard({ adapters }: { adapters: HostNetworkAdapterSummary[] }) {
  return <Card title="网卡信息" extra={`${adapters.length} 个接口`}>
    <Table
      className="nx-responsive-table"
      rowKey="name"
      columns={adapterColumns}
      dataSource={adapters}
      pagination={false}
      tableLayout="fixed"
      locale={{ emptyText: <PageEmpty description="等待首次网络资源扫描" /> }}
    />
  </Card>;
}

function FeatureSupport({ features }: { features: HostFeatureSummary[] }) {
  const supported = features.filter((feature) => feature.status === "supported").length;
  return <Card title="功能支持" extra={`${supported} / ${features.length} 项支持`}>
    <div className="nx-feature-grid">
      {features.map((feature) => <div className="nx-feature-tile" key={feature.key}>
        <div><strong>{feature.name}</strong><span>{feature.description}</span></div>
        <FeatureStatus status={feature.status} />
      </div>)}
    </div>
  </Card>;
}

function FeatureStatus({ status }: { status: string }) {
  if (status === "supported") return <StatusTag label="支持" tone="running" />;
  if (status === "unsupported") return <StatusTag label="不支持" tone="stopped" />;
  return <StatusTag label="需关注" tone="warning" />;
}

function HostMetrics({ data }: { data: HostDetail }) {
  const metric = data.latest_metrics;
  if (!metric) return <Card><PageEmpty description="等待首次节点性能采样" /></Card>;
  const used = metric.memory_total_kib - metric.memory_available_kib;
  const memoryPercent = metric.memory_total_kib
    ? Math.round(used * 100 / metric.memory_total_kib)
    : 0;
  return <div className="nx-metric-grid">
    <FactCard label="1 分钟负载" value={metric.load_1.toFixed(2)} />
    <FactCard label="5 / 15 分钟负载" value={`${metric.load_5.toFixed(2)} / ${metric.load_15.toFixed(2)}`} />
    <Card><span>内存使用</span><strong>{memoryPercent}%</strong><Progress percent={memoryPercent} showInfo={false} size="small" /></Card>
    <FactCard label="运行时间" value={`${Math.floor(metric.uptime_seconds / 3600)} 小时`} />
  </div>;
}

const vmColumns: ColumnsType<VmSummary> = [
  {
    title: "虚拟机",
    render: (_, vm) => <div><a className="nx-resource-link" href={`/hosts/${vm.host_id}/vms/${vm.native_id}`}>{vm.name}</a><small className="nx-technical">{vm.native_id}</small></div>,
  },
  { title: "状态", dataIndex: "state", render: (state: string, vm) => <Space size={6} wrap><VmStatusTag state={state} />{vm.needs_restart && <StatusTag label="待重启" tone="warning" description="配置已修改，重启虚拟机后生效" />}</Space> },
  { title: "配置", render: (_, vm) => `${vm.vcpus ?? "—"} vCPU · ${vm.memory_mib ?? "—"} MiB` },
];

const adapterColumns: ColumnsType<HostNetworkAdapterSummary> = [
  {
    title: "网卡",
    dataIndex: "name",
    render: (name: string, adapter) => <div>
      <strong>{name}</strong>
      <span className="nx-technical">{adapter.mac ?? "MAC 暂未获取"}</span>
    </div>,
  },
  {
    title: "类型",
    dataIndex: "kind",
    width: 150,
    responsive: ["md"],
    render: networkKindLabel,
  },
  {
    title: "链路",
    dataIndex: "state",
    width: 112,
    render: (state: string) => state === "up"
      ? <StatusTag label="已连接" tone="running" />
      : state === "down"
        ? <StatusTag label="未连接" tone="stopped" />
        : <StatusTag label="状态未知" tone="unknown" />,
  },
  {
    title: "用途",
    dataIndex: "management",
    width: 128,
    responsive: ["sm"],
    render: (management: boolean) => management
      ? <StatusTag label="管理链路" tone="warning" />
      : <StatusTag label="普通接口" tone="unknown" />,
  },
];

function networkKindLabel(value: string) {
  const labels: Record<string, string> = {
    physical: "物理网卡", bridge: "Bridge", bond: "Bond", vlan: "VLAN",
    wireless: "无线网卡", unknown: "其他接口",
  };
  return labels[value] ?? value;
}

function resourceTotal(data: HostDetail) {
  return Object.values(data.resource_counts).reduce((total, count) => total + count, 0);
}

function formatTime(value: string | null) {
  return formatDateTime(value, { dateStyle: "medium", timeStyle: "short" }, "等待首次同步");
}
