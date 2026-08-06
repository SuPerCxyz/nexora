import { Alert, Button, Card, Flex, Form, Input, InputNumber, Select, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type { AccountData, AccountUpdate } from "../api/account";
import { loadAccount, logout, updateAccount } from "../api/account";
import { formatDateTime } from "./dateTime";
import { PageError, PageLoading } from "./PageState";
import { StatusTag } from "./StatusTag";

type LoginAttempt = AccountData["login_history"][number];
type AccountFormValues = Omit<AccountUpdate, "density" | "global_monospace">;

export function AccountPage() {
  const [data, setData] = useState<AccountData | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<AccountFormValues>();
  useEffect(() => {
    loadAccount().then((value) => { setData(value); form.setFieldsValue(value.administrator); }).catch(setError);
  }, [form]);
  if (error) return <PageError error={error} />;
  if (!data) return <PageLoading />;
  async function save() {
    setSaving(true);
    try {
      const values = await form.validateFields();
      window.location.assign((await updateAccount({ ...values, density: "comfortable", global_monospace: false })).redirect);
    }
    catch (caught) { setError(caught instanceof Error ? caught : new Error("账户保存失败")); setSaving(false); }
  }
  async function signOut() {
    try { window.location.assign((await logout()).redirect); }
    catch (caught) { setError(caught instanceof Error ? caught : new Error("退出失败")); }
  }
  return <Space orientation="vertical" size={12} className="nx-page-stack">
    <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap><div className="nx-page-title"><Typography.Title level={2}>管理员账户</Typography.Title><Typography.Text type="secondary">更新身份、安全设置和界面偏好</Typography.Text></div></Flex>
    <Alert type="info" showIcon={false} message="保存账户后会撤销其他 Session，并为当前浏览器签发新 Session。" />
    <Card title="账户与偏好">
      <Form form={form} layout="vertical" requiredMark={false} className="nx-form-narrow">
        <Form.Item name="username" label="用户名" rules={[{ required: true }, { pattern: /^[A-Za-z0-9_.-]{3,64}$/, message: "请输入 3-64 位合法用户名" }]}><Input autoComplete="username" /></Form.Item>
        <Form.Item name="current_password" label="当前密码" rules={[{ required: true }]}><Input.Password autoComplete="current-password" /></Form.Item>
        <Form.Item name="new_password" label="新密码" extra="留空表示不修改密码" rules={[{ min: 12, message: "新密码至少 12 位" }]}><Input.Password autoComplete="new-password" /></Form.Item>
        <Form.Item name="confirmation" label="确认新密码" dependencies={["new_password"]} rules={[({ getFieldValue }) => ({ validator(_, value) { return !getFieldValue("new_password") || value === getFieldValue("new_password") ? Promise.resolve() : Promise.reject(new Error("两次密码不一致")); } })]}><Input.Password autoComplete="new-password" /></Form.Item>
        <div className="nx-settings-grid">
          <Form.Item name="session_timeout_minutes" label="Session 超时（分钟）" rules={[{ required: true }]}><InputNumber min={5} max={1440} className="nx-full-width" /></Form.Item>
          <Form.Item name="timezone" label="时区" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="language" label="语言"><Select options={[{ value: "zh-CN", label: "简体中文" }, { value: "en", label: "English" }]} /></Form.Item>
        </div>
        <Space><Button className="nx-btn-primary" loading={saving} onClick={save}>保存账户</Button><Button className="nx-btn-danger" onClick={signOut}>退出登录</Button></Space>
      </Form>
    </Card>
    <Card title="登录历史"><Table rowKey={(item) => `${item.occurred_at}-${item.remote_address}`} columns={historyColumns} dataSource={data.login_history} pagination={false} /></Card>
  </Space>;
}

const historyColumns: ColumnsType<LoginAttempt> = [
  { title: "时间", dataIndex: "occurred_at", render: (value: string) => formatDateTime(value, { dateStyle: "short", timeStyle: "medium" }) },
  { title: "用户名", dataIndex: "username" },
  { title: "来源", dataIndex: "remote_address", render: (value: string) => <span className="nx-technical">{value}</span> },
  { title: "结果", dataIndex: "succeeded", render: (value: boolean) => <StatusTag label={value ? "成功" : "失败"} tone={value ? "running" : "error"} /> },
];
