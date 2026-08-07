import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Steps,
  Typography,
} from "antd";
import { ArrowLeftOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { useState } from "react";

import type { HostOnboardingRequest } from "../api/contracts";
import { beginHostOnboarding } from "../api/hosts";
import { navigateToTask } from "./navigateToTask";

type FormValues = Omit<HostOnboardingRequest, "labels"> & { labels?: string };

export function HostOnboardingPage() {
  const [authenticationMethod, setAuthenticationMethod] = useState("private_key");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(values: FormValues) {
    setSubmitting(true);
    setError(null);
    try {
      const started = await beginHostOnboarding({
        ...values,
        password: authenticationMethod === "password" ? values.password : null,
        private_key: authenticationMethod === "private_key" ? values.private_key : null,
        private_key_passphrase:
          authenticationMethod === "private_key" ? values.private_key_passphrase : null,
        labels: (values.labels ?? "").split(",").map((item) => item.trim()).filter(Boolean),
        notes: values.notes || null,
      });
      navigateToTask(started.location);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "节点 Host Key 扫描失败");
      setSubmitting(false);
    }
  }

  return (
    <Space className="nx-page-stack nx-create-page" orientation="vertical" size={12}>
      <div className="nx-detail-header">
        <Space orientation="vertical" size={6} className="nx-page-title">
          <Button type="link" href="/hosts" icon={<ArrowLeftOutlined />} className="nx-back-link">
            返回节点
          </Button>
          <Typography.Title level={2}>添加 KVM 节点</Typography.Title>
          <Typography.Text type="secondary">
            先扫描并核对 SSH Host Key，确认前不会尝试认证或执行远端命令。
          </Typography.Text>
        </Space>
      </div>
      <Steps current={0} responsive items={[{ title: "连接信息" }, { title: "核对指纹" }, { title: "只读探测" }]} />
      {error && <Alert type="error" showIcon title="无法扫描 SSH Host Key" description={error} />}
      <Card title="节点连接" extra={<SafetyCertificateOutlined />}>
        <Form<FormValues>
          layout="vertical"
          requiredMark="optional"
          initialValues={{
            ssh_port: 22,
            ssh_username: "root",
            authentication_method: "private_key",
            sudo_mode: "passwordless",
          }}
          onFinish={submit}
        >
          <div className="nx-form-grid">
            <Form.Item label="节点名称" name="name" rules={[{ required: true, max: 128 }]}>
              <Input placeholder="例如 compute-01" autoComplete="off" />
            </Form.Item>
            <Form.Item label="管理 IP 或主机名" name="address" rules={[{ required: true, max: 255 }]}>
              <Input className="nx-technical-input" placeholder="192.0.2.10" autoComplete="off" />
            </Form.Item>
            <Form.Item label="SSH 端口" name="ssh_port" rules={[{ required: true }]}>
              <InputNumber min={1} max={65535} />
            </Form.Item>
            <Form.Item label="SSH 用户名" name="ssh_username" rules={[{ required: true, max: 64 }]}>
              <Input autoComplete="username" />
            </Form.Item>
            <Form.Item label="认证方式" name="authentication_method" rules={[{ required: true }]}>
              <Select onChange={setAuthenticationMethod} options={[
                { value: "private_key", label: "SSH 私钥" },
                { value: "password", label: "SSH 密码" },
              ]} />
            </Form.Item>
            <Form.Item label="sudo 模式" name="sudo_mode" rules={[{ required: true }]}>
              <Select options={[
                { value: "passwordless", label: "免密 sudo" },
                { value: "none", label: "root / 不使用 sudo" },
              ]} />
            </Form.Item>
          </div>
          {authenticationMethod === "password" ? (
            <Form.Item label="SSH 密码" name="password" rules={[{ required: true, max: 4096 }]}>
              <Input.Password autoComplete="new-password" />
            </Form.Item>
          ) : (
            <>
              <Form.Item label="SSH 私钥" name="private_key" rules={[{ required: true }]}>
                <Input.TextArea className="nx-technical-input" rows={7} spellCheck={false} />
              </Form.Item>
              <Form.Item label="私钥口令" name="private_key_passphrase">
                <Input.Password autoComplete="new-password" />
              </Form.Item>
            </>
          )}
          <Form.Item label="标签" name="labels" extra="使用英文逗号分隔，最多 32 个。">
            <Input placeholder="production, edge" />
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={3} maxLength={4000} showCount />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            title="此步骤只扫描 SSH Host Key"
            description="凭据会加密保存，但只有在下一步明确确认指纹后才用于连接。"
          />
          <div className="nx-form-actions nx-form-actions-end">
            <Button type="primary" htmlType="submit" loading={submitting}>扫描 SSH Host Key</Button>
          </div>
        </Form>
      </Card>
    </Space>
  );
}
