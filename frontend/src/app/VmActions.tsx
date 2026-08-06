import { Alert, Button, Dropdown, Flex, Input, Modal, Popconfirm, Space } from "antd";
import { useState } from "react";

import type { ConsoleCredential } from "../api/consoles";
import { createConsole } from "../api/consoles";
import type { VmDetail, VmLifecycleAction } from "../api/contracts";
import { submitVmLifecycle } from "../api/core";
import { VmConsoleModal } from "./VmConsoleModal";
import { VmCloneModal } from "./VmCloneModal";
import { VmMigrateModal } from "./VmMigrateModal";
import { VmRemoveModal } from "./VmRemoveModal";

type DangerousAction = "force_off" | "force_reboot";

export function VmActions({ data }: { data: VmDetail }) {
  const [loading, setLoading] = useState<VmLifecycleAction | null>(null);
  const [dangerousAction, setDangerousAction] = useState<DangerousAction | null>(null);
  const [confirmationName, setConfirmationName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [consoleLoading, setConsoleLoading] = useState<"vnc" | "serial" | null>(null);
  const [consoleCredential, setConsoleCredential] = useState<ConsoleCredential | null>(null);
  const [cloneOpen, setCloneOpen] = useState(false);
  const [migrateOpen, setMigrateOpen] = useState(false);
  const [removeMode, setRemoveMode] = useState<"delete" | "rename" | null>(null);
  const writable = ["managed", "transient"].includes(data.configuration_status);
  const state = data.vm.state.toLowerCase();

  async function run(action: VmLifecycleAction, confirmation?: string) {
    setLoading(action);
    setError(null);
    try {
      const task = await submitVmLifecycle(data.vm.host_id, data.vm.native_id, action, confirmation);
      window.location.assign(task.location);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "虚拟机操作提交失败");
      setLoading(null);
    }
  }

  async function openConsole(kind: "vnc" | "serial") {
    setConsoleLoading(kind);
    setError(null);
    try { setConsoleCredential(await createConsole(data.vm.host_id, data.vm.native_id, kind)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "控制台创建失败"); }
    finally { setConsoleLoading(null); }
  }

  const dangerousItems = [
    { key: "force_off", label: "强制关机", danger: true },
    { key: "force_reboot", label: "强制重启", danger: true },
  ];

  return (
    <section className="nx-vm-actions" aria-labelledby="vm-actions-title">
      <Flex justify="space-between" align="center" gap={16} wrap>
        <div>
          <strong id="vm-actions-title">虚拟机操作</strong>
          <span>操作将进入任务队列，并在执行前再次校验资源版本。</span>
        </div>
        <Flex className="nx-vm-action-buttons" justify="flex-end" wrap gap={8}>
          {data.active && <Button className="nx-btn-special" loading={consoleLoading === "vnc"} onClick={() => openConsole("vnc")}>VNC 控制台</Button>}
          {data.active && <Button className="nx-btn-special" loading={consoleLoading === "serial"} onClick={() => openConsole("serial")}>串口控制台</Button>}
          {writable && !data.active && data.persistent && (
            <Button className="nx-btn-positive" loading={loading === "start"} onClick={() => run("start")}>启动</Button>
          )}
          {writable && !data.active && data.persistent && (
            <Button className="nx-btn-info" onClick={() => setCloneOpen(true)}>完整克隆</Button>
          )}
          {writable && !data.active && data.persistent && (
            <Button className="nx-btn-info" onClick={() => setMigrateOpen(true)}>关机迁移</Button>
          )}
          {writable && state === "running" && <RunningActions loading={loading} run={run} />}
          {writable && state === "paused" && (
            <Button className="nx-btn-positive" loading={loading === "resume"} onClick={() => run("resume")}>恢复</Button>
          )}
          {writable && data.persistent && (
            <Button
              className={data.autostart ? "nx-btn-danger" : "nx-btn-positive"}
              loading={loading === (data.autostart ? "autostart_disable" : "autostart_enable")}
              onClick={() => run(data.autostart ? "autostart_disable" : "autostart_enable")}
            >{data.autostart ? "禁用自动启动" : "启用自动启动"}</Button>
          )}
          {writable && data.active && data.persistent && (
            <ConfirmAction label="保存运行状态" description="虚拟机将停止并保存当前运行状态。" loading={loading === "managed_save"} onConfirm={() => run("managed_save")} />
          )}
          {writable && !data.active && data.persistent && (
            <Button className="nx-btn-info" onClick={() => setRemoveMode("rename")}>重命名</Button>
          )}
        </Flex>
      </Flex>
      {(writable && data.active) || (writable && !data.active && data.persistent) ? (
        <Flex className="nx-vm-danger-row" justify="flex-end" align="center" gap={8}>
          <span className="nx-vm-danger-label">危险操作</span>
          {writable && data.active && (
            <Dropdown menu={{ items: dangerousItems, onClick: ({ key }) => setDangerousAction(key as DangerousAction) }}>
              <Button className="nx-btn-danger">强制操作</Button>
            </Dropdown>
          )}
          {writable && !data.active && data.persistent && (
            <Button className="nx-btn-danger" onClick={() => setRemoveMode("delete")}>删除</Button>
          )}
        </Flex>
      ) : null}
      {error && <Alert type="error" showIcon={false} message={error} />}
      <DangerousActionModal
        action={dangerousAction}
        vmName={data.vm.name}
        confirmationName={confirmationName}
        loading={loading === dangerousAction}
        onNameChange={setConfirmationName}
        onCancel={() => { setDangerousAction(null); setConfirmationName(""); }}
        onConfirm={() => dangerousAction && run(dangerousAction, confirmationName)}
      />
      <VmConsoleModal credential={consoleCredential} onClose={() => setConsoleCredential(null)} />
      <VmCloneModal data={data} open={cloneOpen} onClose={() => setCloneOpen(false)} />
      <VmMigrateModal data={data} open={migrateOpen} onClose={() => setMigrateOpen(false)} />
      <VmRemoveModal data={data} open={removeMode !== null} mode={removeMode ?? "delete"} onClose={() => setRemoveMode(null)} />
    </section>
  );
}

function RunningActions({
  loading,
  run,
}: {
  loading: VmLifecycleAction | null;
  run: (action: VmLifecycleAction) => Promise<void>;
}) {
  return <>
    <ConfirmAction label="正常关机" description="系统将向客户机发送正常关机请求。" loading={loading === "shutdown"} onConfirm={() => run("shutdown")} />
    <ConfirmAction label="正常重启" description="系统将向客户机发送正常重启请求。" loading={loading === "reboot"} onConfirm={() => run("reboot")} />
    <Button className="nx-btn-warning" loading={loading === "pause"} onClick={() => run("pause")}>暂停</Button>
  </>;
}

function ConfirmAction({
  label,
  description,
  loading,
  onConfirm,
}: {
  label: string;
  description: string;
  loading: boolean;
  onConfirm: () => void;
}) {
  return (
    <Popconfirm title={label} description={description} okText="确认" cancelText="取消" onConfirm={onConfirm}>
      <Button className={label === "保存运行状态" ? "nx-btn-info" : "nx-btn-warning"} loading={loading}>{label}</Button>
    </Popconfirm>
  );
}

function DangerousActionModal({
  action,
  vmName,
  confirmationName,
  loading,
  onNameChange,
  onCancel,
  onConfirm,
}: {
  action: DangerousAction | null;
  vmName: string;
  confirmationName: string;
  loading: boolean;
  onNameChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const label = action === "force_reboot" ? "强制重启" : "强制关机";
  return (
    <Modal
      title={label}
      open={action !== null}
      okText={label}
      cancelText="取消"
      okButtonProps={{ danger: true, disabled: confirmationName !== vmName, loading }}
      onCancel={onCancel}
      onOk={onConfirm}
      destroyOnHidden
    >
      <Space orientation="vertical" size={12} className="nx-page-stack">
        <Alert type="error" showIcon={false} message="强制操作可能造成客户机数据损坏。" />
        <label htmlFor="vm-danger-confirmation">输入虚拟机名称 {vmName} 以确认</label>
        <Input id="vm-danger-confirmation" value={confirmationName} onChange={(event) => onNameChange(event.target.value)} autoComplete="off" />
      </Space>
    </Modal>
  );
}
