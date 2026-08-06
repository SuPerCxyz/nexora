import { Card, Flex, Space, Typography } from "antd";

import { StatusTag } from "./StatusTag";

export function PreviewPage() {
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
    </Space>
  );
}
