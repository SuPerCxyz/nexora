import { Alert, Button, Card, Empty, Flex, Modal, Result, Skeleton, Space, Tooltip, Typography } from "antd";
import { useState } from "react";

import { StatusTag } from "./StatusTag";

export function PreviewPage() {
  const [modalOpen, setModalOpen] = useState(false);
  return (
    <Space orientation="vertical" size={12} className="nx-page-stack">
      <Flex className="nx-detail-header" justify="space-between" align="start" wrap gap={16}>
        <div>
          <Typography.Title level={2}>Ant Design 基础平台</Typography.Title>
          <Typography.Text type="secondary">P8-001 安全预览入口</Typography.Text>
        </div>
        <StatusTag label="会话正常" tone="running" />
      </Flex>
      <Card title="迁移状态">
        <div className="nx-preview-row"><strong>核心只读页面</strong><span>总览、节点与虚拟机列表</span><StatusTag label="迁移中" tone="warning" /></div>
        <div className="nx-preview-row"><strong>运行边界</strong><span>单容器、无运行时 Node.js</span><StatusTag label="正常" tone="running" /></div>
      </Card>
      <Card title="内容完整性">
        <div className="nx-preview-content-grid">
          <div><span>技术标识（单行省略）</span><Tooltip title="provider-name/super-long-model-name-version-2026-08-12-preview"><code className="nx-technical">provider-name/super-long-model-name-version-2026-08-12-preview</code></Tooltip></div>
          <div><span>数值与单位（不可拆分）</span><strong className="nx-number-unit">12.4 MiB</strong></div>
          <div className="nx-preview-description"><span>允许多行内容</span><p>connection refused while requesting https://very-long-host.example.internal/api/v1/resources；错误消息、URL 与说明文字应在容器内合理换行，不撑破页面。</p></div>
        </div>
      </Card>
      <Card title="受控页面状态">
        <Alert type="warning" showIcon title="部分数据不可用" description="拓扑数据暂时不可用，其余只读资源仍可正常查看。" />
        <div className="nx-preview-state-grid">
          <Card size="small" title="Loading"><Skeleton active paragraph={{ rows: 3 }} /></Card>
          <Card size="small" title="Empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" /></Card>
          <Card size="small" title="Error"><Result status="error" title="组件加载失败" subTitle="connection refused while requesting a long internal resource URL" /></Card>
          <Card size="small" title="404"><Result status="404" title="页面不存在" /></Card>
        </div>
      </Card>
      <Card title="弹层边界">
        <Button onClick={() => setModalOpen(true)}>打开长内容测试弹窗</Button>
      </Card>
      <Modal title="很长的弹窗标题用于验证关闭按钮、正文滚动与底部操作在窄屏下始终可用" open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => setModalOpen(false)} okText="确认" cancelText="取消">
        <Typography.Paragraph>该弹窗仅用于视觉回归，不提交任何业务操作。</Typography.Paragraph>
        <pre className="nx-code">{Array.from({ length: 18 }, (_, index) => `${index + 1}. provider-name/super-long-model-name-version-2026-08-12-preview`).join("\n")}</pre>
      </Modal>
    </Space>
  );
}
