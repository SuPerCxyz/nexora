import { Button, Card, Flex, Select, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type { NetworkEdge, NetworkNode, NetworkOverview } from "../api/network";
import { loadNetworks } from "../api/network";
import { NetworkChangeModal } from "./NetworkChangeModal";
import { NetworkTopologyGraph } from "./NetworkTopologyGraph";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { StatusTag } from "./StatusTag";

export function NetworkPage() {
  const [data, setData] = useState<NetworkOverview | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [changeKind, setChangeKind] = useState<"bridge" | "vlan" | null>(null);
  useEffect(() => { loadNetworks().then(setData).catch(setError); }, []);
  async function selectHost(hostId: string) {
    try { setData(await loadNetworks(hostId)); }
    catch (caught) { setError(caught instanceof Error ? caught : new Error("网络拓扑读取失败")); }
  }
  if (error) return <PageError error={error} />;
  if (!data) return <PageLoading />;
  const topology = data.topology;
  return <Space orientation="vertical" size={20} className="nx-page-stack">
    <Flex className="nx-detail-header" justify="space-between" align="end" gap={16} wrap>
      <div><Typography.Title level={2}>宿主机网络</Typography.Title><Typography.Text type="secondary">接口、Bridge、VLAN、vnet 与虚拟机关系</Typography.Text></div>
      <Space wrap>
        <Select aria-label="节点" value={data.selected_host_id} options={data.hosts.map((host) => ({ value: host.id, label: host.name }))} onChange={selectHost} className="nx-host-select" placeholder="选择节点" />
        {data.selected_host_id && <Button className="nx-btn-primary" onClick={() => setChangeKind("bridge")}>创建 Bridge</Button>}
        {data.selected_host_id && <Button className="nx-btn-info" onClick={() => setChangeKind("vlan")}>创建 VLAN</Button>}
      </Space>
    </Flex>
    {!topology ? <Card><PageEmpty description="添加并扫描 KVM 节点后显示网络资源" /></Card> : <>
      <div className="nx-fact-grid">
        <Fact label="拓扑节点" value={topology.nodes.length} />
        <Fact label="拓扑关系" value={topology.edges.length} />
        <Fact label="告警" value={topology.warning_count} />
        <Fact label="管理链路" value={topology.nodes.filter((node) => node.management).length} />
      </div>
      <Card title="拓扑图"><NetworkTopologyGraph nodes={topology.nodes} edges={topology.edges} /><Typography.Text type="secondary">可拖拽节点并使用滚轮缩放；下方表格提供完整可访问数据。</Typography.Text></Card>
      <Card title="拓扑节点"><Table className="nx-responsive-table" rowKey="id" columns={nodeColumns} dataSource={topology.nodes} pagination={false} tableLayout="fixed" /></Card>
      <Card title="拓扑关系"><Table className="nx-responsive-table" rowKey="id" columns={edgeColumns} dataSource={topology.edges} pagination={false} tableLayout="fixed" /></Card>
    </>}
    {data.selected_host_id && <NetworkChangeModal hostId={data.selected_host_id} kind={changeKind ?? "bridge"} open={changeKind !== null} onClose={() => setChangeKind(null)} />}
  </Space>;
}

function Fact({ label, value }: { label: string; value: number }) {
  return <Card size="small" className="nx-fact-card"><span>{label}</span><strong>{value}</strong></Card>;
}

const nodeColumns: ColumnsType<NetworkNode> = [
  { title: "名称", dataIndex: "label", render: (value: string, node) => <div><strong className="nx-technical">{value}</strong><small className="nx-mobile-table-detail">{node.node_type}</small></div> },
  { title: "类型", dataIndex: "node_type", width: 150, responsive: ["md"] },
  { title: "状态", dataIndex: "status", width: 112, render: (value: string) => <NetworkStatusTag status={value} /> },
  { title: "标记", width: 260, responsive: ["lg"], render: (_, node) => <Space wrap>{node.management && <StatusTag label="管理链路" tone="warning" />}{node.default_route && <StatusTag label="默认路由" tone="running" />}{node.warnings.map((warning) => <StatusTag key={warning} label={warning} tone="warning" />)}</Space> },
];

function NetworkStatusTag({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  if (normalized === "up") return <StatusTag label="已连接" tone="running" />;
  if (normalized === "down") return <StatusTag label="未连接" tone="stopped" />;
  if (normalized === "unknown") return <StatusTag label="状态未知" tone="unknown" />;
  return <StatusTag label="需要关注" tone="warning" />;
}

const edgeColumns: ColumnsType<NetworkEdge> = [
  { title: "来源", dataIndex: "source", render: (value: string, edge) => <div><span className="nx-technical">{value}</span><small className="nx-mobile-table-detail">{edge.relation} → {edge.target}</small></div> },
  { title: "关系", dataIndex: "relation", width: 160, responsive: ["md"] },
  { title: "目标", dataIndex: "target", responsive: ["md"], render: (value: string) => <span className="nx-technical">{value}</span> },
  { title: "风险", dataIndex: "warnings", width: 220, responsive: ["lg"], render: (warnings: string[]) => <Space wrap>{warnings.map((warning) => <StatusTag key={warning} label={warning} tone="warning" />)}</Space> },
];
