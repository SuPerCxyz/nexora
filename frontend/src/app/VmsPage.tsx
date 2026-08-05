import { Button, Card, Flex, Pagination, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type { PaginatedResponse, VmSummary } from "../api/contracts";
import { loadVms } from "../api/core";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { VmStatusTag } from "./StatusTag";

const PAGE_SIZE = 20;

export function VmsPage() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<PaginatedResponse<VmSummary> | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setError(null);
    loadVms(page, PAGE_SIZE).then(setData).catch(setError);
  }, [page, reload]);

  if (error) return <PageError error={error} retry={() => setReload((value) => value + 1)} />;
  if (!data) return <PageLoading />;
  return (
    <Space orientation="vertical" size={20} className="nx-page-stack">
      <Flex justify="space-between" align="center" gap={12}>
        <Typography.Title level={2}>虚拟机</Typography.Title>
        <Button type="primary" href="/vms/create">创建虚拟机</Button>
      </Flex>
      {data.total === 0 ? <Card><PageEmpty description="尚未发现虚拟机，添加节点后会自动只读扫描" /></Card> : <>
        <Table className="nx-desktop-table" rowKey="resource_id" columns={columns} dataSource={data.items} pagination={false} />
        <div className="nx-mobile-list">{data.items.map((vm) => <VmCard key={vm.resource_id} vm={vm} />)}</div>
        <Pagination current={page} pageSize={PAGE_SIZE} total={data.total} showSizeChanger={false} onChange={setPage} />
      </>}
    </Space>
  );
}

const columns: ColumnsType<VmSummary> = [
  { title: "虚拟机", render: (_, vm) => <VmLink vm={vm} /> },
  { title: "状态", dataIndex: "state", render: (state: string) => <VmStatusTag state={state} /> },
  { title: "节点", dataIndex: "host_name" },
  { title: "配置", render: (_, vm) => `${vm.vcpus ?? "—"} vCPU · ${vm.memory_mib ?? "—"} MiB` },
];

function VmCard({ vm }: { vm: VmSummary }) {
  return <Card><Flex justify="space-between" align="start" gap={12}><VmLink vm={vm} /><VmStatusTag state={vm.state} /></Flex><div className="nx-card-facts"><span>{vm.host_name}</span><span>{vm.vcpus ?? "—"} vCPU · {vm.memory_mib ?? "—"} MiB</span></div></Card>;
}

function VmLink({ vm }: { vm: VmSummary }) {
  return <div><a className="nx-resource-link" href={`/hosts/${vm.host_id}/vms/${vm.native_id}`}>{vm.name}</a><small className="nx-technical">{vm.native_id}</small></div>;
}
