import { Card, Flex, Pagination, Select, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type { AuditItem, AuditPage as AuditPayload } from "../api/audit";
import { loadAudit } from "../api/audit";
import { formatDateTime } from "./dateTime";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { StatusTag } from "./StatusTag";

export function AuditPage() {
  const initial = new URLSearchParams(window.location.search);
  const initialPage = Math.max(1, Number(initial.get("page")) || 1);
  const [data, setData] = useState<AuditPayload | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [hostId, setHostId] = useState<string | undefined>(initial.get("host_id") || undefined);
  const [outcome, setOutcome] = useState(initial.get("outcome") || "all");
  useEffect(() => { loadAudit(initialPage, hostId, outcome).then(setData).catch(setError); }, []);
  function apply(page = 1, nextHost = hostId, nextOutcome = outcome) {
    setError(null);
    loadAudit(page, nextHost, nextOutcome).then(setData).catch(setError);
  }
  useEffect(() => {
    const params = new URLSearchParams();
    if (hostId) params.set("host_id", hostId);
    if (outcome !== "all") params.set("outcome", outcome);
    if (data && data.page > 1) params.set("page", String(data.page));
    const query = params.toString();
    const newPath = query ? `/audit?${query}` : "/audit";
    if (window.location.pathname + window.location.search !== newPath) {
      window.history.replaceState({}, "", newPath);
    }
  }, [hostId, outcome, data]);
  if (error) return <PageError error={error} />;
  if (!data) return <PageLoading />;
  return <Space orientation="vertical" size={12} className="nx-page-stack">
    <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap>
      <div className="nx-page-title"><Typography.Title level={2}>远端命令审计</Typography.Title><Typography.Text type="secondary">仅展示已脱敏摘要，凭据、Token 与敏感输出不会入库</Typography.Text></div>
      <Space wrap>
        <Select allowClear showSearch placeholder="全部节点" className="nx-filter-control" value={hostId} options={data.hosts.map((host) => ({ value: host.id, label: host.name }))} onChange={(value) => { setHostId(value); apply(1, value, outcome); }} />
        <Select className="nx-filter-control" value={outcome} options={[{ value: "all", label: "全部结果" }, { value: "succeeded", label: "成功" }, { value: "failed", label: "失败" }, { value: "timed_out", label: "超时" }]} onChange={(value) => { setOutcome(value); apply(1, hostId, value); }} />
      </Space>
    </Flex>
    <Card title={`最近记录 · ${data.total} 条`}>
      <Table className="nx-responsive-table" rowKey="operation_id" columns={columns} dataSource={data.items} pagination={false} locale={{ emptyText: <PageEmpty description="没有匹配的审计记录" /> }} scroll={{ x: 980 }} tableLayout="fixed" expandable={{ rowExpandable: (item) => Boolean(item.stdout_summary || item.stderr_summary), expandedRowRender: AuditOutput }} />
      <Pagination className="nx-table-footer" current={data.page} pageSize={50} total={data.total} showSizeChanger={false} onChange={(page) => apply(page)} />
    </Card>
  </Space>;
}

const columns: ColumnsType<AuditItem> = [
  { title: "时间 / Operation", render: (_, item) => <div>{formatDateTime(item.occurred_at, { dateStyle: "short", timeStyle: "medium" })}<div className="nx-technical">{item.operation_id}</div></div> },
  { title: "节点", render: (_, item) => <div>{item.host_name}<div className="nx-technical">{item.host_id}</div></div> },
  { title: "命令摘要", dataIndex: "command_summary", render: (value: string) => <code className="nx-command-summary">{value}</code> },
  { title: "结果", render: (_, item) => <div><StatusTag label={outcomeLabel(item.outcome)} tone={item.outcome === "succeeded" ? "running" : item.outcome === "timed_out" ? "warning" : "error"} /><div className="nx-technical">exit={item.exit_code}</div></div> },
];

function AuditOutput(item: AuditItem) {
  return <Space orientation="vertical" size={12} className="nx-page-stack">{item.stdout_summary && <Output label="stdout" value={item.stdout_summary} />}{item.stderr_summary && <Output label="stderr" value={item.stderr_summary} />}</Space>;
}

function Output({ label, value }: { label: string; value: string }) {
  return <div><strong>{label}</strong><pre className="nx-code nx-audit-output"><code>{value}</code></pre></div>;
}

function outcomeLabel(value: string) {
  return ({ succeeded: "成功", failed: "失败", timed_out: "超时", cancelled: "已取消" } as Record<string, string>)[value] ?? value;
}
