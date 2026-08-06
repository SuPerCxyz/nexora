import { Tag, Tooltip } from "antd";

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

const hostStates: Record<string, [string, StatusTone, string]> = {
  ready: ["连接正常", "running", "节点可连接，可进行只读探测与资源管理"],
  degraded: ["能力受限", "warning", "节点 SSH 可达但核心能力缺失或受限（virsh、sudo、libvirt 等必需项未通过），部分功能不可用；可在节点详情页的“功能支持”中查看缺失项"],
  pending_host_key: ["待确认", "warning", "SSH 主机密钥待管理员确认后才能连接"],
  scanning: ["同步中", "starting", "正在探测节点能力或刷新资源索引"],
  removal_pending: ["待移除", "deleting", "节点已进入移除流程，等待执行"],
  inaccessible: ["连接异常", "error", "无法通过 SSH 连接节点，请检查网络与凭据"],
};

const vmStates: Record<string, [string, StatusTone, string]> = {
  running: ["运行中", "running", "虚拟机正在运行"],
  starting: ["启动中", "starting", "虚拟机正在启动"],
  shutdown: ["关闭中", "stopping", "虚拟机正在关闭"],
  stopping: ["关闭中", "stopping", "虚拟机正在关闭"],
  restarting: ["重启中", "restarting", "虚拟机正在重启"],
  migrating: ["迁移中", "migrating", "虚拟机正在迁移到其他节点"],
  paused: ["已暂停", "paused", "虚拟机已暂停，CPU 被冻结"],
  pmsuspended: ["已暂停", "paused", "虚拟机处于 ACPI 挂起状态"],
  shutoff: ["已关机", "stopped", "虚拟机已关机"],
  "shut off": ["已关机", "stopped", "虚拟机已关机"],
  crashed: ["异常退出", "error", "虚拟机异常退出，请查看控制台日志"],
  blocked: ["已锁定", "locked", "虚拟机被 libvirt 锁定，无法操作"],
};

export function HostStatusTag({ status }: { status: string }) {
  const [label, tone, description] = hostStates[status] ?? ["状态未知", "unknown", "节点状态无法识别"];
  return <StatusTag label={label} tone={tone} description={description} />;
}

export function VmStatusTag({ state }: { state: string }) {
  const [label, tone, description] = vmStates[state] ?? ["状态未知", "unknown", "虚拟机状态无法识别"];
  return <StatusTag label={label} tone={tone} description={description} />;
}

export function StatusTag({
  label,
  tone,
  description,
}: {
  label: string;
  tone: StatusTone;
  description?: string;
}) {
  const tag = <Tag className={`nx-status-tag nx-status-${tone}`}>{label}</Tag>;
  if (!description) return tag;
  return <Tooltip title={description}><span>{tag}</span></Tooltip>;
}
