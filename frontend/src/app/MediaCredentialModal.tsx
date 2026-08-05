import { Alert, Button, Modal, Space, Typography } from "antd";
import { useState } from "react";

import type { IssuedMediaCredential } from "../api/media";
import { revokeMediaCredential } from "../api/media";
import { formatDateTime } from "./dateTime";

export function MediaCredentialModal({
  credential,
  onClose,
}: {
  credential: IssuedMediaCredential | null;
  onClose: () => void;
}) {
  const [revoking, setRevoking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function revoke() {
    if (!credential) return;
    setRevoking(true);
    try { await revokeMediaCredential(credential.credential_id); onClose(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "凭据撤销失败"); setRevoking(false); }
  }
  return <Modal title="ISO 访问凭据" open={credential !== null} onCancel={onClose} footer={null} maskClosable={false} destroyOnHidden>
    {credential && <Space orientation="vertical" size={16} className="nx-page-stack">
      <Alert type="warning" showIcon={false} message="Bearer Token 只显示一次，不得写入日志或 URL。" />
      <CredentialValue label="Content URL" value={credential.content_url} />
      <CredentialValue label="Bearer Token" value={credential.token} />
      <Typography.Text type="secondary">有效期至 {formatDateTime(credential.expires_at, { dateStyle: "short", timeStyle: "medium" })}</Typography.Text>
      {error && <Alert type="error" showIcon={false} message={error} />}
      <Space><Button onClick={onClose}>关闭</Button><Button className="nx-btn-danger" loading={revoking} onClick={revoke}>立即撤销</Button></Space>
    </Space>}
  </Modal>;
}

function CredentialValue({ label, value }: { label: string; value: string }) {
  async function copy() { await navigator.clipboard.writeText(value); }
  return <div className="nx-credential-value"><strong>{label}</strong><pre className="nx-code"><code>{value}</code></pre><Button className="nx-btn-info" size="small" onClick={copy}>复制</Button></div>;
}
