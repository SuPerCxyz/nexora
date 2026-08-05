import { Card, Flex, Space, Typography } from "antd";
import { useEffect, useState } from "react";

import type { OverviewSummary } from "../api/contracts";
import { loadOverview } from "../api/core";
import { PageError, PageLoading } from "./PageState";
import { StatusTag } from "./StatusTag";

export function OverviewPage() {
  const [summary, setSummary] = useState<OverviewSummary | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setError(null);
    loadOverview().then(setSummary).catch(setError);
  }, [reload]);

  if (error) return <PageError error={error} retry={() => setReload((value) => value + 1)} />;
  if (!summary) return <PageLoading />;
  const healthy = summary.host_total > 0 && summary.host_ready === summary.host_total;
  const attention = summary.failed_tasks > 0;

  return (
    <Space orientation="vertical" size={20} className="nx-page-stack">
      <Flex justify="space-between" align="center" wrap gap={12}>
        <Typography.Title level={2}>总览</Typography.Title>
        <StatusTag
          label={attention ? `${summary.failed_tasks} 项需关注` : healthy ? "运行正常" : "等待节点状态"}
          tone={attention ? "error" : healthy ? "running" : "unknown"}
        />
      </Flex>
      <div className="nx-metric-grid">
        <Metric title="节点在线" value={`${summary.host_ready} / ${summary.host_total}`} href="/hosts" />
        <Metric title="虚拟机运行" value={`${summary.vm_running} / ${summary.vm_total}`} href="/vms" />
        <Metric title="进行中" value={String(summary.active_tasks)} href="/tasks" />
        <Metric title="需关注" value={String(summary.failed_tasks)} href="/tasks" />
      </div>
      <Card title="子系统状态" className="nx-system-card">
        <SystemRow name="计算节点" detail={`${summary.host_ready} 个可达 · ${summary.host_total - summary.host_ready} 个待处理`} href="/hosts" label={summary.host_total ? (healthy ? "正常" : "需关注") : "未接入"} tone={healthy ? "running" : summary.host_total ? "warning" : "unknown"} />
        <SystemRow name="虚拟机" detail={`${summary.vm_running} 个运行中 · ${summary.vm_total - summary.vm_running} 个已停止`} href="/vms" label={summary.vm_total ? "正常" : "未发现"} tone={summary.vm_total ? "running" : "unknown"} />
        <SystemRow name="资源同步" detail={`${summary.host_synced} / ${summary.host_total} 个节点已同步`} href="/hosts" label={summary.host_synced ? "已同步" : "待同步"} tone={summary.host_synced ? "running" : "unknown"} />
      </Card>
    </Space>
  );
}

function Metric({ title, value, href }: { title: string; value: string; href: string }) {
  return <a href={href} className="nx-metric-link"><Card size="small"><Typography.Text type="secondary">{title}</Typography.Text><strong>{value}</strong></Card></a>;
}

function SystemRow({ name, detail, href, label, tone }: { name: string; detail: string; href: string; label: string; tone: "running" | "warning" | "unknown" }) {
  return <a className="nx-system-row" href={href}><strong>{name}</strong><span>{detail}</span><StatusTag label={label} tone={tone} /><b aria-hidden>›</b></a>;
}
