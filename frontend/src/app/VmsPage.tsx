import { Button, Card, Flex, Pagination, Select, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type { HostSummary, PaginatedResponse, VmSummary } from "../api/contracts";
import { loadHosts, loadVms } from "../api/core";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { StatusTag, VmStatusTag } from "./StatusTag";

const PAGE_SIZE = 20;

const stateOptions = [
  { value: "running", label: "运行中" },
  { value: "paused", label: "已暂停" },
  { value: "shut off", label: "已停止" },
];

export function VmsPage() {
  const initial = new URLSearchParams(window.location.search);
  const [page, setPage] = useState(() => Number(initial.get("page")) || 1);
  const [data, setData] = useState<PaginatedResponse<VmSummary> | null>(null);
  const [hosts, setHosts] = useState<HostSummary[]>([]);
  const [state, setState] = useState<string | undefined>(initial.get("state") || undefined);
  const [hostId, setHostId] = useState<string | undefined>(initial.get("host_id") || undefined);
  const [error, setError] = useState<Error | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    loadHosts(1, 100).then((response) => setHosts(response.items)).catch(() => {});
  }, []);

  useEffect(() => {
    setPage(1);
  }, [state, hostId]);

  useEffect(() => {
    setError(null);
    loadVms(page, PAGE_SIZE, state, hostId).then(setData).catch(setError);
  }, [page, state, hostId, reload]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (page > 1) params.set("page", String(page));
    if (state) params.set("state", state);
    if (hostId) params.set("host_id", hostId);
    const query = params.toString();
    const newPath = query ? `/vms?${query}` : "/vms";
    if (window.location.pathname + window.location.search !== newPath) {
      window.history.replaceState({}, "", newPath);
    }
  }, [page, state, hostId]);

  if (error) return <PageError error={error} retry={() => setReload((value) => value + 1)} />;
  if (!data) return <PageLoading />;
  return (
    <Space orientation="vertical" size={12} className="nx-page-stack">
      <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap>
        <div className="nx-page-title"><Typography.Title level={2}>虚拟机</Typography.Title><Typography.Text type="secondary">管理 KVM 虚拟机与生命周期</Typography.Text></div>
        <Flex gap={8} wrap align="center">
          <Select allowClear placeholder="状态" className="nx-filter-control" options={stateOptions} value={state} onChange={setState} />
          <Select allowClear showSearch placeholder="节点" className="nx-filter-control" options={hosts.map((host) => ({ value: host.id, label: host.name }))} value={hostId} onChange={setHostId} />
          <Button type="primary" href="/vms/create">创建虚拟机</Button>
        </Flex>
      </Flex>
      {data.total === 0 ? <Card><PageEmpty description="没有匹配的虚拟机" /></Card> : <>
        <Card><Table className="nx-desktop-table" rowKey="resource_id" columns={columns} dataSource={data.items} pagination={false} /></Card>
        <div className="nx-mobile-list">{data.items.map((vm) => <VmCard key={vm.resource_id} vm={vm} />)}</div>
        <Pagination current={page} pageSize={PAGE_SIZE} total={data.total} showSizeChanger={false} onChange={setPage} />
      </>}
    </Space>
  );
}

const columns: ColumnsType<VmSummary> = [
  { title: "虚拟机", render: (_, vm) => <VmLink vm={vm} /> },
  { title: "状态", dataIndex: "state", render: (state: string, vm) => <RestartBadge state={state} needsRestart={vm.needs_restart} /> },
  { title: "节点", dataIndex: "host_name" },
  { title: "配置", render: (_, vm) => `${vm.vcpus ?? "—"} vCPU · ${vm.memory_mib ?? "—"} MiB` },
];

function VmCard({ vm }: { vm: VmSummary }) {
  return <Card><Flex justify="space-between" align="start" gap={12}><VmLink vm={vm} /><VmStatusTag state={vm.state} /></Flex><div className="nx-card-facts"><span>{vm.host_name}</span><span>{vm.vcpus ?? "—"} vCPU · {vm.memory_mib ?? "—"} MiB</span></div></Card>;
}

function VmLink({ vm }: { vm: VmSummary }) {
  return <div><a className="nx-resource-link" href={`/hosts/${vm.host_id}/vms/${vm.native_id}`}>{vm.name}</a><small className="nx-technical">{vm.native_id}</small></div>;
}

export function RestartBadge({ state, needsRestart }: { state: string; needsRestart?: boolean }) {
  return <Space size={6} wrap><VmStatusTag state={state} />{needsRestart && <StatusTag label="待重启" tone="warning" description="配置已修改，重启虚拟机后生效" />}</Space>;
}
