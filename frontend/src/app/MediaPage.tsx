import { Button, Card, Flex, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type { MediaItemSummary } from "../api/contracts";
import type { IssuedMediaCredential } from "../api/media";
import { issueMediaCredential, loadMedia, scanMedia } from "../api/media";
import { MediaCredentialModal } from "./MediaCredentialModal";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { StatusTag } from "./StatusTag";

export function MediaPage() {
  const [items, setItems] = useState<MediaItemSummary[] | null>(null);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [scanning, setScanning] = useState(false);
  const [credential, setCredential] = useState<IssuedMediaCredential | null>(null);
  const [issuingId, setIssuingId] = useState<string | null>(null);
  useEffect(() => { loadMedia().then((data) => { setItems(data.items); setActiveTaskId(data.active_task_id); }).catch(setError); }, []);
  if (error) return <PageError error={error} />;
  if (!items) return <PageLoading />;
  async function scan() {
    setScanning(true);
    try { window.location.assign((await scanMedia()).location); }
    catch (caught) { setError(caught instanceof Error ? caught : new Error("媒体扫描提交失败")); setScanning(false); }
  }
  async function issue(itemId: string) {
    setIssuingId(itemId);
    try { setCredential(await issueMediaCredential(itemId)); }
    catch (caught) { setError(caught instanceof Error ? caught : new Error("访问凭据创建失败")); }
    finally { setIssuingId(null); }
  }
  return <Space orientation="vertical" size={12} className="nx-page-stack">
    <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap>
      <div><Typography.Title level={2}>平台媒体库</Typography.Title><Typography.Text type="secondary">只读索引平台镜像与 ISO，原始文件不会被修改</Typography.Text></div>
      {activeTaskId ? <Button className="nx-btn-info" href={`/tasks/${activeTaskId}`}>查看扫描任务</Button> : <Button className="nx-btn-primary" loading={scanning} onClick={scan}>扫描媒体库</Button>}
    </Flex>
    <Card><Table rowKey="id" columns={columns(issue, issuingId)} dataSource={items} locale={{ emptyText: <PageEmpty description="尚未建立媒体索引" /> }} pagination={{ pageSize: 20 }} scroll={{ x: 900 }} /></Card>
    <MediaCredentialModal credential={credential} onClose={() => setCredential(null)} />
  </Space>;
}

function columns(issue: (itemId: string) => void, issuingId: string | null): ColumnsType<MediaItemSummary> { return [
  { title: "文件", render: (_, item) => <div><strong>{item.file_name}</strong><div className="nx-technical">{item.relative_path}</div></div> },
  { title: "类型", render: (_, item) => item.image_format ?? item.kind },
  { title: "分类", render: (_, item) => <div>{item.classification ?? "—"}<div className="nx-technical">{item.architecture ?? ""}</div></div> },
  { title: "大小", dataIndex: "size_bytes", render: formatBytes },
  { title: "SHA-256", dataIndex: "sha256", ellipsis: true, render: (value: string) => <span className="nx-technical">{value}</span> },
  { title: "状态", dataIndex: "status", render: (value: string) => <StatusTag label={value === "available" ? "可用" : value === "missing" ? "缺失" : "不可访问"} tone={value === "available" ? "running" : value === "missing" ? "stopped" : "error"} /> },
  { title: "操作", fixed: "right", render: (_, item) => <MediaActions item={item} issuing={issuingId === item.id} onIssue={() => issue(item.id)} /> },
]; }

function MediaActions({ item, issuing, onIssue }: { item: MediaItemSummary; issuing: boolean; onIssue: () => void }) {
  if (item.status !== "available") return null;
  if (item.kind === "iso") return <Button size="small" className="nx-btn-info" loading={issuing} onClick={onIssue}>创建访问凭据</Button>;
  return <Space><Button size="small" className="nx-btn-info" href={`/media/${item.id}/copy`}>复制到节点</Button>{item.standalone && <Button size="small" className="nx-btn-primary" href="/vms/create/platform-image">创建虚拟机</Button>}</Space>;
}

function formatBytes(value: number) {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GiB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  return `${(value / 1024).toFixed(1)} KiB`;
}
