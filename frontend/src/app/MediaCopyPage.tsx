import { Alert, Button, Card, Flex, Form, Input, Select, Space, Typography } from "antd";
import { useEffect, useState } from "react";

import type { MediaCopyOptions } from "../api/media";
import { copyMedia, loadMediaCopy } from "../api/media";
import { navigateToTask } from "./navigateToTask";
import { PageEmpty, PageError, PageLoading } from "./PageState";

export function MediaCopyPage({ mediaId }: { mediaId: string }) {
  const [data, setData] = useState<MediaCopyOptions | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();
  useEffect(() => {
    loadMediaCopy(mediaId).then((value) => {
      setData(value);
      form.setFieldsValue({ target_file_name: value.item.file_name });
    }).catch(setError);
  }, [form, mediaId]);
  if (error) return <PageError error={error} />;
  if (!data) return <PageLoading />;
  async function submit() {
    setSubmitting(true);
    try { navigateToTask((await copyMedia(mediaId, await form.validateFields())).location); }
    catch (caught) { if (caught instanceof Error) setError(caught); setSubmitting(false); }
  }
  return <Space orientation="vertical" size={12} className="nx-page-stack">
    <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap><div className="nx-page-title"><Typography.Title level={2}>复制 {data.item.file_name}</Typography.Title><Typography.Text type="secondary">源镜像保持只读，校验完成后才发布目标文件</Typography.Text></div></Flex>
    <Alert type="info" showIcon={false} title="任务使用专属 .partial 文件，完成大小与 SHA-256 校验后发布，并拒绝覆盖同名文件。" />
    <Card>
      {data.targets.length === 0 ? <PageEmpty description="没有 active 的 dir 或 netfs 目标存储池" /> : <Form form={form} layout="vertical" requiredMark={false} className="nx-form-narrow">
        <Form.Item name="pool_resource_id" label="目标存储池" rules={[{ required: true }]}>
          <Select options={data.targets.map((target) => ({ value: target.pool_resource_id, label: `${target.host_name} · ${target.pool_name} · ${target.target_path}` }))} />
        </Form.Item>
        <Form.Item name="target_file_name" label="目标文件名" rules={[{ required: true }, { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]{0,250}\.(qcow2|raw)$/, message: "请输入 qcow2 或 raw 文件名" }]}><Input className="nx-technical-input" /></Form.Item>
        <Space><Button href="/media">取消</Button><Button type="primary" loading={submitting} onClick={submit}>创建复制任务</Button></Space>
      </Form>}
    </Card>
  </Space>;
}
