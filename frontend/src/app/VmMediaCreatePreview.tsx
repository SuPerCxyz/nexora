import { Alert, Button, Card, Descriptions, Space } from "antd";

import type { VmMediaCreatePreview as Preview } from "../api/contracts";

export function VmMediaCreatePreview({
  preview,
  loading,
  error,
  onBack,
  onConfirm,
}: {
  preview: Preview;
  loading: boolean;
  error: string | null;
  onBack: () => void;
  onConfirm: () => void;
}) {
  const summary = preview.summary;
  return (
    <Space className="nx-create-sections" orientation="vertical" size={16}>
      {error && <Alert type="error" showIcon title="无法创建任务" description={error} />}
      <div className="nx-preview-grid">
        <Card title="计划摘要">
          <Descriptions column={1} size="small" items={[
            { key: "name", label: "名称", children: summary.name },
            { key: "host", label: "节点", children: summary.host_name },
            { key: "media", label: "源镜像", children: summary.media_name },
            { key: "pool", label: "目标 Pool", children: summary.pool_name },
            { key: "target", label: "目标路径", children: <code>{summary.target_path}</code> },
            { key: "sha", label: "SHA-256", children: <code>{summary.source_sha256}</code> },
            { key: "compute", label: "计算规格", children: `${summary.vcpus} vCPU · ${summary.memory_mib} MiB` },
            { key: "capacity", label: "目标容量", children: summary.target_capacity_bytes ? formatBytes(summary.target_capacity_bytes) : "保持源容量" },
            { key: "network", label: "网络", children: summary.network },
            { key: "iso", label: "安装 ISO", children: summary.iso_name ?? "无" },
            { key: "driver", label: "Driver ISO", children: summary.driver_iso_name ?? "无" },
            { key: "firmware", label: "启动方式", children: firmwareLabel(summary) },
            { key: "tpm", label: "TPM 2.0", children: summary.tpm2 ? "启用" : "未启用" },
            { key: "cloud", label: "Cloud-init", children: summary.cloud_init ?? "未启用" },
          ]} />
        </Card>
        <Card title="Domain XML Diff">
          <pre className="nx-code nx-code-light" aria-label="Domain XML Diff">{preview.diff_text}</pre>
        </Card>
      </div>
      <Alert type="warning" showIcon title="确认后创建可恢复任务" description="任务将复制并校验镜像、发现新 Volume、生成可选 NoCloud seed，最后定义保持关机的虚拟机。" />
      <div className="nx-form-actions">
        <Button onClick={onBack}>返回修改</Button>
        <Button type="primary" loading={loading} onClick={onConfirm}>确认并创建任务</Button>
      </div>
    </Space>
  );
}

function firmwareLabel(summary: Preview["summary"]): string {
  if (summary.firmware !== "uefi") return "BIOS";
  return summary.secure_boot ? "UEFI · Secure Boot" : "UEFI · 非安全启动";
}

function formatBytes(value: number): string {
  return `${(value / 1024 / 1024 / 1024).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} GiB`;
}
