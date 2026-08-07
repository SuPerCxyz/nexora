import { Alert, Button, Card, Form, Input, Typography } from "antd";

export function AuthPage({ mode, error, csrf }: { mode: string; error: string | null; csrf: string }) {
  const initialize = mode === "initialize";
  const submit = (values: Record<string, string>) => submitAuthentication(
    initialize ? "/initialize" : "/login",
    { ...values, csrf_token: csrf },
  );
  return <main className="nx-auth-page"><Card className="nx-auth-card">
    <Typography.Title level={1}>{initialize ? "创建本地管理员" : "管理员登录"}</Typography.Title>
    <Typography.Paragraph type="secondary">{initialize ? "建立 Nexora 的唯一管理员账户" : "登录后管理虚拟机、节点、存储与网络"}</Typography.Paragraph>
    {error && <Alert type="error" showIcon title={error} />}
    <Form layout="vertical" onFinish={submit}>
      <Form.Item label="管理员用户名" name="username" rules={[{ required: true }]}><Input autoComplete="username" maxLength={64} autoFocus /></Form.Item>
      <Form.Item label="密码" name="password" rules={[{ required: true }]}><Input.Password autoComplete={initialize ? "new-password" : "current-password"} /></Form.Item>
      {initialize && <Form.Item label="确认密码" name="confirmation" dependencies={["password"]} rules={[{ required: true }, ({ getFieldValue }) => ({ validator(_, value) { return !value || getFieldValue("password") === value ? Promise.resolve() : Promise.reject(new Error("两次输入的密码不一致")); } })]}><Input.Password autoComplete="new-password" /></Form.Item>}
      <Button type="primary" htmlType="submit" block>{initialize ? "创建管理员并进入系统" : "登录"}</Button>
    </Form>
  </Card></main>;
}

function submitAuthentication(action: string, values: Record<string, string>) {
  const form = document.createElement("form");
  form.method = "post";
  form.action = action;
  Object.entries(values).forEach(([name, value]) => {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    form.append(input);
  });
  document.body.append(form);
  form.submit();
}
