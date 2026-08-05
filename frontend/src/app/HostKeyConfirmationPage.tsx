import { Alert, Button, Card, Checkbox, Descriptions, Space, Spin, Steps, Typography } from "antd";
import { ArrowLeftOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";

import type { HostKeyConfirmation } from "../api/contracts";
import { confirmHostKey, loadHostKeyConfirmation } from "../api/hosts";
import { PageError } from "./PageState";

export function HostKeyConfirmationPage({ hostId }: { hostId: string }) {
  const [confirmation, setConfirmation] = useState<HostKeyConfirmation | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [confirmationError, setConfirmationError] = useState<string | null>(null);

  useEffect(() => {
    loadHostKeyConfirmation(hostId).then(setConfirmation).catch(setError);
  }, [hostId]);

  async function confirm() {
    if (!confirmation) return;
    setSubmitting(true);
    setConfirmationError(null);
    try {
      const task = await confirmHostKey(hostId, confirmation.host_key_digest);
      window.location.assign(task.location);
    } catch (caught) {
      setConfirmationError(caught instanceof Error ? caught.message : "Host Key 确认失败");
      setSubmitting(false);
    }
  }

  if (error) return <PageError error={error} />;
  if (!confirmation) return <Spin fullscreen description="正在读取 Host Key" />;

  return (
    <Space className="nx-page-stack nx-create-page" orientation="vertical" size={24}>
      <div className="nx-detail-header">
        <Space orientation="vertical" size={6}>
          <Button type="link" href="/hosts" icon={<ArrowLeftOutlined />} className="nx-back-link">返回节点</Button>
          <Typography.Title level={2}>确认 SSH Host Key</Typography.Title>
          <Typography.Text type="secondary">确认后才会尝试 SSH 认证并开始只读能力探测。</Typography.Text>
        </Space>
      </div>
      <Steps current={1} responsive items={[{ title: "连接信息" }, { title: "核对指纹" }, { title: "只读探测" }]} />
      {confirmationError && <Alert type="error" showIcon title="连接已阻止" description={confirmationError} />}
      <Alert
        type="warning"
        showIcon
        title="必须通过节点控制台或可信渠道核对指纹"
        description="Nexora 不会自动信任变化的 Host Key，也不会覆盖已有信任记录。"
      />
      <Card title="待确认指纹" extra={<SafetyCertificateOutlined />}>
        <Descriptions column={{ xs: 1, sm: 2 }} items={[
          { key: "name", label: "节点", children: confirmation.name },
          { key: "endpoint", label: "目标地址", children: <code>{confirmation.endpoint}</code> },
        ]} />
        <div className="nx-fingerprint-list">
          {confirmation.fingerprints.map((item) => (
            <div className="nx-fingerprint" key={`${item.key_type}-${item.fingerprint}`}>
              <Typography.Text strong>{item.key_type}</Typography.Text>
              <code>{item.fingerprint}</code>
            </div>
          ))}
        </div>
        <Checkbox checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)}>
          我已通过可信渠道核对以上全部指纹
        </Checkbox>
        <div className="nx-form-actions nx-form-actions-end">
          <Button type="primary" disabled={!acknowledged} loading={submitting} onClick={confirm}>
            指纹一致，确认并开始只读探测
          </Button>
        </div>
      </Card>
    </Space>
  );
}
