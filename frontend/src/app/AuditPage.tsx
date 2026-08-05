import { Button, Card, Flex, Select, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type { AuditItem, AuditPage as AuditPayload } from "../api/audit";
import { loadAudit } from "../api/audit";
import { formatDateTime } from "./dateTime";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { StatusTag } from "./StatusTag";

export function AuditPage() {
  const [data, setData] = useState<AuditPayload | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [hostId, setHostId] = useState<string | undefined>();
  const [outcome, setOutcome] = useState("all");
  useEffect(() => { loadAudit().then(setData).catch(setError); }, []);
  async function refresh(page = 1, nextHost = hostId, nextOutcome = outcome) {
    try { setData(await loadAudit(page, nextHost, nextOutcome)); }
    catch (caught) { setError(caught instanceof Error ? caught : new Error("审计记录读取失败")); }
  }
  if (error) return <PageError error={error} />;
  if (!data) return <PageLoading />;
  return <Space orientation="vertical" size={20} className="nx-page-stack">
    <div className="nx-page-title"><Typography.Title level={2}>远端命令审计</Typography.Title><Typography.Text type="secondary">仅展示已脱敏摘要，凭据、Token 与敏感输出不会入库</Typography.Text></div>
    <Card>
      <Flex gap={12} align="end" wrap>
        <div><label className="nx-field-label">节点</label><Select allowClear placeholder="全部节点" value={hostId} options={data.hosts.map((host) => ({ value: host.id, label: host.name }))} onChange={setHostId} className="nx-filter-control" /></div>
        <div><label className="nx-field-label">结果</label><Select value={outcome} options={[{ value: "all", label: "全部" }, { value: "succeeded", label: "成功" }, { value: "failed", label: "失败" }]} onChange={setOutcome} className="nx-filter-control" /></div>
        <Button className="nx-btn-primary" onClick={() => refresh()}>筛选</Button>
      </Flex>
    </Card>
    <Card title={`最近记录 · ${data.total} 条`}>
      <Table rowKey="operation_id" columns={columns} dataSource={data.items} pagination={false} locale={{ emptyText: <PageEmpty description="没有匹配的审计记录" /> }} scroll={{ x: 980 }} expandable={{ rowExpandable: (item) => Boolean(item.stdout_summary || item.stderr_summary), expandedRowRender: AuditOutput }} />
      <Flex justify="space-between" align="center" className="nx-table-footer"><Button disabled={!data.has_previous} onClick={() => refresh(data.page - 1)}>上一页</Button><span>第 {data.page} 页</span><Button disabled={!data.has_next} onClick={() => refresh(data.page + 1)}>下一页</Button></Flex>
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
