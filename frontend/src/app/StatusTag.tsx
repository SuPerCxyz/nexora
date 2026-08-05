import { Tag } from "antd";

export type StatusTone =
  | "running"
  | "starting"
  | "stopping"
  | "restarting"
  | "migrating"
  | "creating"
  | "deleting"
  | "error"
  | "warning"
  | "paused"
  | "maintenance"
  | "unknown"
  | "stopped"
  | "locked";

const hostStates: Record<string, [string, StatusTone]> = {
  ready: ["连接正常", "running"],
  degraded: ["性能下降", "warning"],
  pending_host_key: ["待确认", "warning"],
  scanning: ["同步中", "starting"],
  removal_pending: ["待移除", "deleting"],
  inaccessible: ["连接异常", "error"],
};

const vmStates: Record<string, [string, StatusTone]> = {
  running: ["运行中", "running"],
  starting: ["启动中", "starting"],
  shutdown: ["关闭中", "stopping"],
  stopping: ["关闭中", "stopping"],
  restarting: ["重启中", "restarting"],
  migrating: ["迁移中", "migrating"],
  paused: ["已暂停", "paused"],
  pmsuspended: ["已暂停", "paused"],
  shutoff: ["已关机", "stopped"],
  "shut off": ["已关机", "stopped"],
  crashed: ["异常退出", "error"],
  blocked: ["已锁定", "locked"],
};

export function HostStatusTag({ status }: { status: string }) {
  const [label, tone] = hostStates[status] ?? ["状态未知", "unknown"];
  return <StatusTag label={label} tone={tone} />;
}

export function VmStatusTag({ state }: { state: string }) {
  const [label, tone] = vmStates[state] ?? ["状态未知", "unknown"];
  return <StatusTag label={label} tone={tone} />;
}

export function StatusTag({ label, tone }: { label: string; tone: StatusTone }) {
  return <Tag className={`nx-status-tag nx-status-${tone}`}>{label}</Tag>;
}
