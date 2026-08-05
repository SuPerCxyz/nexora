import { Button, Space, Spin, Steps, Typography } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";

import type {
  VmMediaCreateOptions,
  VmMediaCreatePreview,
  VmMediaCreatePreviewRequest,
} from "../api/contracts";
import {
  applyVmMediaCreate,
  loadVmMediaCreateOptions,
  previewVmMediaCreate,
} from "../api/vmMediaCreate";
import { PageError } from "./PageState";
import { VmMediaCreateForm } from "./VmMediaCreateForm";
import { VmMediaCreatePreview as PreviewPanel } from "./VmMediaCreatePreview";

export function VmMediaCreatePage() {
  const [options, setOptions] = useState<VmMediaCreateOptions | null>(null);
  const [preview, setPreview] = useState<VmMediaCreatePreview | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadVmMediaCreateOptions().then(setOptions).catch(setError);
  }, []);

  async function createPreview(values: VmMediaCreatePreviewRequest) {
    setSubmitting(true);
    setActionError(null);
    try {
      setPreview(await previewVmMediaCreate(values));
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "平台镜像创建计划预览失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function confirmPreview() {
    if (!preview) return;
    setSubmitting(true);
    setActionError(null);
    try {
      const task = await applyVmMediaCreate(preview);
      window.location.assign(task.location);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "平台镜像创建任务失败");
      setSubmitting(false);
    }
  }

  if (error) return <PageError error={error} />;
  if (!options) return <Spin fullscreen description="正在加载平台镜像与目标资源" />;

  return (
    <Space className="nx-page-stack nx-create-page" orientation="vertical" size={24}>
      <div className="nx-detail-header">
        <Space orientation="vertical" size={6}>
          <Button type="link" href="/vms/create" icon={<ArrowLeftOutlined />} className="nx-back-link">返回现有 Volume 创建</Button>
          <Typography.Title level={2}>从平台镜像创建虚拟机</Typography.Title>
          <Typography.Text type="secondary">复制校验完成后再定义虚拟机，可选 Cloud-init、扩容和 UEFI 启动。</Typography.Text>
        </Space>
      </div>
      <Steps current={preview ? 1 : 0} responsive items={[{ title: "配置" }, { title: "预览差异" }, { title: "确认执行" }]} />
      {preview ? (
        <PreviewPanel
          preview={preview}
          loading={submitting}
          error={actionError}
          onBack={() => { setPreview(null); setActionError(null); }}
          onConfirm={confirmPreview}
        />
      ) : (
        <VmMediaCreateForm options={options} loading={submitting} error={actionError} onSubmit={createPreview} />
      )}
    </Space>
  );
}
