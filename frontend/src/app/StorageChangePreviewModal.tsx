import { Alert, Descriptions, Modal } from "antd";

import type { StorageChangePreview } from "../api/contracts";

export function StorageChangePreviewModal({
  preview,
  loading,
  error,
  onCancel,
  onConfirm,
}: {
  preview: StorageChangePreview | null;
  loading: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!preview) return null;
  const deleting = preview.operation.includes("delete");
  return (
    <Modal
      width={880}
      open
      title="检查存储配置"
      okText={deleting ? "确认删除并执行" : "确认并执行"}
      okButtonProps={{ danger: deleting }}
      confirmLoading={loading}
      onOk={onConfirm}
      onCancel={onCancel}
      destroyOnHidden
    >
      {error && <Alert className="nx-section-alert" type="error" showIcon title="无法提交存储变更" description={error} />}
      <Alert
        className="nx-section-alert"
        type={deleting ? "error" : "warning"}
        showIcon
        title={deleting ? "删除不可自动回滚" : "执行前会重新扫描权威资源"}
        description={deleting ? "任何引用、版本变化或身份不一致都会阻止删除。" : "名称、UUID、容量或基础版本变化都会阻止执行。"}
      />
      <Descriptions size="small" column={{ xs: 1, sm: 2 }} items={Object.entries(preview.summary).map(([key, value]) => ({ key, label: labels[key] ?? key, children: displayValue(value) }))} />
      <pre className="nx-code nx-code-light nx-modal-code" aria-label="XML Diff">{preview.diff_text}</pre>
    </Modal>
  );
}

const labels: Record<string, string> = {
  name: "名称",
  pool_type: "类型",
  target_path: "目标路径",
  pool_uuid: "Pool UUID",
  start: "立即启动",
  autostart: "自动启动",
  pool_name: "目标 Pool",
  volume_format: "格式",
  capacity_bytes: "容量（bytes）",
};

function displayValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "是" : "否";
  return value === null || value === undefined ? "—" : String(value);
}
