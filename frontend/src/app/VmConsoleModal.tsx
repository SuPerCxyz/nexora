import { Modal, Spin, Typography } from "antd";
import { lazy, Suspense } from "react";

import type { ConsoleCredential } from "../api/consoles";
const SerialConsole = lazy(() => import("./SerialConsole").then((module) => ({ default: module.SerialConsole })));
const VncConsole = lazy(() => import("./VncConsole").then((module) => ({ default: module.VncConsole })));

export function VmConsoleModal({ credential, onClose }: { credential: ConsoleCredential | null; onClose: () => void }) {
  const title = credential?.kind === "serial" ? "串口控制台" : "VNC 控制台";
  return <Modal title={title} open={credential !== null} onCancel={onClose} footer={null} width="min(1120px, calc(100vw - 24px))" destroyOnHidden>
    <Suspense fallback={<Spin size="large" />}>{credential?.kind === "serial" ? <SerialConsole credential={credential} /> : credential ? <VncConsole credential={credential} /> : null}</Suspense>
    <Typography.Text type="secondary">会话空闲 5 分钟或持续 60 分钟后自动关闭，内容不会写入 Nexora 数据库。</Typography.Text>
  </Modal>;
}
