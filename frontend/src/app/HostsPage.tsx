import { Button, Card, Flex, Pagination, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type { HostSummary, PaginatedResponse } from "../api/contracts";
import { loadHosts } from "../api/core";
import { formatDateTime } from "./dateTime";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { HostStatusTag } from "./StatusTag";

const PAGE_SIZE = 20;

export function HostsPage() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<PaginatedResponse<HostSummary> | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setError(null);
    loadHosts(page, PAGE_SIZE).then(setData).catch(setError);
  }, [page, reload]);

  if (error) return <PageError error={error} retry={() => setReload((value) => value + 1)} />;
  if (!data) return <PageLoading />;
  return (
    <Space orientation="vertical" size={12} className="nx-page-stack">
      <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap>
        <div className="nx-page-title"><Typography.Title level={2}>节点</Typography.Title><Typography.Text type="secondary">管理已纳管的 KVM 计算节点</Typography.Text></div>
        <Button type="primary" href="/hosts/new">添加节点</Button>
      </Flex>
      {data.total === 0 ? <Card><PageEmpty description="尚未添加节点" /></Card> : <>
        <Card><Table className="nx-desktop-table" rowKey="id" columns={columns} dataSource={data.items} pagination={false} /></Card>
        <div className="nx-mobile-list">{data.items.map((host) => <HostCard key={host.id} host={host} />)}</div>
        <Pagination current={page} pageSize={PAGE_SIZE} total={data.total} showSizeChanger={false} onChange={setPage} />
      </>}
    </Space>
  );
}

const columns: ColumnsType<HostSummary> = [
  { title: "节点", render: (_, host) => <ResourceLink href={`/hosts/${host.id}`} name={host.name} technical={host.id} /> },
  { title: "连接", render: (_, host) => <><span className="nx-technical">{host.address}</span><small>SSH {host.ssh_port}</small></> },
  { title: "状态", dataIndex: "status", render: (status: string) => <HostStatusTag status={status} /> },
  { title: "上次同步", dataIndex: "last_scanned_at", render: formatTime },
];

function HostCard({ host }: { host: HostSummary }) {
  return <Card><Flex justify="space-between" align="start" gap={12}><ResourceLink href={`/hosts/${host.id}`} name={host.name} technical={host.address} /><HostStatusTag status={host.status} /></Flex><div className="nx-card-facts"><span>SSH {host.ssh_port}</span><span>{formatTime(host.last_scanned_at)}</span></div></Card>;
}

function ResourceLink({ href, name, technical }: { href: string; name: string; technical: string }) {
  return <div><a className="nx-resource-link" href={href}>{name}</a><small className="nx-technical">{technical}</small></div>;
}

function formatTime(value: string | null) {
  return formatDateTime(value, { dateStyle: "medium", timeStyle: "short" }, "等待首次同步");
}
