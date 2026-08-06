import { Alert, Button, Card, Flex, Progress, Select, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type { HostSummary, TaskDetail, TaskStepSummary, TaskSummary } from "../api/contracts";
import { loadHosts } from "../api/core";
import { cancelTask, loadTask, loadTasks, recoverTask } from "../api/tasks";
import { formatDateTime } from "./dateTime";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { StatusTag } from "./StatusTag";

const statusOptions = [
  { value: "pending", label: "等待中" },
  { value: "queued", label: "已排队" },
  { value: "running", label: "执行中" },
  { value: "waiting_confirmation", label: "等待确认" },
  { value: "succeeded", label: "已完成" },
  { value: "failed", label: "失败" },
  { value: "cancelled", label: "已取消" },
  { value: "timed_out", label: "超时" },
  { value: "interrupted", label: "已中断" },
];

export function TasksPage() {
  const [items, setItems] = useState<TaskSummary[] | null>(null);
  const [hosts, setHosts] = useState<HostSummary[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>();
  const [hostFilter, setHostFilter] = useState<string>();
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => { loadTasks().then((payload) => setItems(payload.items)).catch(setError); }, []);
  useEffect(() => { loadHosts(1, 100).then((payload) => setHosts(payload.items)).catch(() => {}); }, []);
  if (error) return <PageError error={error} />;
  if (!items) return <PageLoading />;
  const filtered = items.filter((task) =>
    (!statusFilter || task.status === statusFilter) &&
    (!hostFilter || task.host_id === hostFilter));
  return <Space orientation="vertical" size={12} className="nx-page-stack">
    <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap>
      <div className="nx-page-title"><Typography.Title level={2}>任务中心</Typography.Title><Typography.Text type="secondary">跟踪资源变更、恢复与验证进度</Typography.Text></div>
      <Space wrap>
        <Select allowClear placeholder="状态" className="nx-filter-control" options={statusOptions} value={statusFilter} onChange={setStatusFilter} />
        <Select allowClear showSearch placeholder="节点" className="nx-filter-control" options={hosts.map((host) => ({ value: host.id, label: host.name }))} value={hostFilter} onChange={setHostFilter} />
      </Space>
    </Flex>
    <Card><Table className="nx-responsive-table" rowKey="id" columns={taskColumns} dataSource={filtered} locale={{ emptyText: <PageEmpty description="没有匹配的任务记录" /> }} pagination={{ pageSize: 20 }} tableLayout="fixed" /></Card>
  </Space>;
}

export function TaskDetailPage({ taskId }: { taskId: string }) {
  const [data, setData] = useState<TaskDetail | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    let active = true;
    const refresh = () => loadTask(taskId).then((value) => active && setData(value)).catch(setError);
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => { active = false; window.clearInterval(timer); };
  }, [taskId]);
  if (error) return <PageError error={error} />;
  if (!data) return <PageLoading />;
  const task = data.task;
  const cancellable = ["pending", "queued", "running", "waiting_confirmation"].includes(task.status);
  const recoverable = task.status === "interrupted" && task.resumable && task.retry_count < task.max_retries;
  async function submit(action: "cancel" | "recover") {
    setSubmitting(true);
    try {
      if (action === "cancel") await cancelTask(taskId); else await recoverTask(taskId);
      setData(await loadTask(taskId));
    } catch (caught) { setError(caught instanceof Error ? caught : new Error("任务操作失败")); }
    finally { setSubmitting(false); }
  }
  return <Space orientation="vertical" size={12} className="nx-page-stack">
    <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap>
      <div><Typography.Title level={2}>{task.title}</Typography.Title><span className="nx-technical">{task.id}</span></div>
      <Space>{cancellable && <Button className="nx-btn-danger" loading={submitting} onClick={() => submit("cancel")}>请求取消</Button>}{recoverable && <Button className="nx-btn-primary" loading={submitting} onClick={() => submit("recover")}>验证并重试</Button>}</Space>
    </Flex>
    {task.status === "interrupted" && <Alert type="warning" showIcon={false} message="任务因进程中断而停止，不会自动重放远端写操作。" />}
    {task.error_message && <Alert type="error" showIcon={false} message={task.error_message} />}
    <div className="nx-fact-grid"><TaskFact label="状态" value={<TaskStatus value={task.status} />} /><TaskFact label="进度" value={<Progress percent={Math.round(task.progress)} size="small" />} /><TaskFact label="步骤" value={<strong>{task.current_step} / {task.total_steps}</strong>} /></div>
    <Card title="执行步骤"><Table className="nx-responsive-table" rowKey="sequence" columns={stepColumns} dataSource={data.steps} pagination={false} locale={{ emptyText: <PageEmpty description="任务尚未开始执行步骤" /> }} tableLayout="fixed" /></Card>
  </Space>;
}

function TaskFact({ label, value }: { label: string; value: React.ReactNode }) {
  return <Card size="small" className="nx-fact-card"><span>{label}</span>{value}</Card>;
}

function TaskStatus({ value }: { value: string }) {
  const labels: Record<string, string> = {
    pending: "等待中", queued: "已排队", running: "执行中", waiting_confirmation: "等待确认",
    cancel_requested: "正在取消", cancelled: "已取消", succeeded: "已完成", failed: "失败",
    timed_out: "超时", interrupted: "已中断", recovering: "恢复中", unknown: "未知",
  };
  const tones: Record<string, "running" | "starting" | "warning" | "error" | "stopped" | "unknown"> = {
    succeeded: "running", running: "starting", recovering: "starting", pending: "unknown",
    queued: "unknown", waiting_confirmation: "warning", cancel_requested: "warning",
    cancelled: "stopped", failed: "error", timed_out: "error", interrupted: "warning", unknown: "unknown",
  };
  return <StatusTag label={labels[value] ?? value} tone={tones[value] ?? "unknown"} />;
}

const taskColumns: ColumnsType<TaskSummary> = [
  { title: "任务", dataIndex: "title", render: (value: string, task) => <div><a href={`/tasks/${task.id}`}>{value}</a><div className="nx-technical">{task.id}</div></div> },
  { title: "状态", dataIndex: "status", width: 96, render: (value: string) => <TaskStatus value={value} /> },
  { title: "进度", dataIndex: "progress", render: (value: number) => <Progress percent={Math.round(value)} size="small" /> },
  { title: "步骤", width: 80, responsive: ["md"], render: (_, task) => `${task.current_step} / ${task.total_steps}` },
  { title: "创建时间", dataIndex: "created_at", width: 180, responsive: ["lg"], render: formatDate },
];

const stepColumns: ColumnsType<TaskStepSummary> = [
  { title: "#", dataIndex: "sequence", width: 64, responsive: ["md"] },
  { title: "名称", dataIndex: "name" },
  { title: "状态", dataIndex: "status", width: 96, render: (value: string) => <TaskStatus value={value} /> },
  { title: "尝试", dataIndex: "attempt_count", width: 72, responsive: ["md"] },
  { title: "开始", dataIndex: "started_at", width: 180, responsive: ["lg"], render: formatDate },
  { title: "结束", dataIndex: "finished_at", width: 180, responsive: ["lg"], render: formatDate },
];

function formatDate(value: string | null) {
  return formatDateTime(value, { dateStyle: "short", timeStyle: "medium" });
}
