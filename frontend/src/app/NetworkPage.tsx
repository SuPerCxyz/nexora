import { Button, Card, Flex, Select, Space, Table, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";

import type { NetworkEdge, NetworkNode, NetworkOverview } from "../api/network";
import { loadNetworks } from "../api/network";
import { NetworkChangeModal } from "./NetworkChangeModal";
import { NetworkTopologyGraph } from "./NetworkTopologyGraph";
import { FactCard } from "./FactCard";
import {
  defaultRouteInfo,
  managementInfo,
  nodeTypeColor,
  nodeTypeInfo,
  nodeTypeLabels,
  relationInfo,
  warningInfo,
} from "./networkLabels";
import { PageEmpty, PageError, PageLoading } from "./PageState";
import { StatusTag } from "./StatusTag";

const legendTypes = ["physical", "vlan", "bridge", "vnet", "vm_nic", "virtual_machine"] as const;
const legendItems = legendTypes.map((type) => ({
  type,
  label: nodeTypeLabels[type].label,
  color: nodeTypeColor[type],
}));

export function NetworkPage() {
  const initial = new URLSearchParams(window.location.search);
  const [data, setData] = useState<NetworkOverview | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [changeKind, setChangeKind] = useState<"bridge" | "vlan" | null>(null);
  useEffect(() => { loadNetworks(initial.get("host_id") || undefined).then(setData).catch(setError); }, []);
  async function selectHost(hostId: string | undefined) {
    try { setData(await loadNetworks(hostId)); }
    catch (caught) { setError(caught instanceof Error ? caught : new Error("网络拓扑读取失败")); }
  }
  useEffect(() => {
    if (!data?.selected_host_id) return;
    const params = new URLSearchParams();
    params.set("host_id", data.selected_host_id);
    const newPath = `/networks?${params.toString()}`;
    if (window.location.pathname + window.location.search !== newPath) {
      window.history.replaceState({}, "", newPath);
    }
  }, [data?.selected_host_id]);
  if (error) return <PageError error={error} />;
  if (!data) return <PageLoading />;
  const topology = data.topology;
  return <Space orientation="vertical" size={12} className="nx-page-stack">
    <Flex className="nx-detail-header" justify="space-between" align="start" gap={16} wrap>
      <div className="nx-page-title"><Typography.Title level={2}>宿主机网络</Typography.Title><Typography.Text type="secondary">接口、Bridge、VLAN、vnet 与虚拟机关系</Typography.Text></div>
      <Space wrap>
        <Select aria-label="节点" value={data.selected_host_id} options={data.hosts.map((host) => ({ value: host.id, label: host.name }))} onChange={selectHost} className="nx-host-select" placeholder="选择节点" />
        {data.selected_host_id && <Button type="primary" onClick={() => setChangeKind("bridge")}>创建 Bridge</Button>}
        {data.selected_host_id && <Button className="nx-btn-info" onClick={() => setChangeKind("vlan")}>创建 VLAN</Button>}
      </Space>
    </Flex>
    {!topology ? <Card><PageEmpty description="添加并扫描 KVM 节点后显示网络资源" /></Card> : <>
      <div className="nx-metric-grid">
        <FactCard label="拓扑节点" value={topology.nodes.length} />
        <FactCard label="拓扑关系" value={topology.edges.length} />
        <FactCard label="告警" value={topology.warning_count} />
        <Tooltip title={managementInfo.description}><span><FactCard label="管理链路" value={topology.nodes.filter((node) => node.management).length} /></span></Tooltip>
      </div>
      <Card title="拓扑图">
        <NetworkTopologyGraph nodes={topology.nodes} edges={topology.edges} />
        <div className="nx-topology-legend">{legendItems.map((item) => <span key={item.type} className="nx-legend-item"><i className="nx-legend-swatch" style={{ background: item.color }} aria-hidden /><span>{item.label}</span></span>)}</div>
        <Typography.Text type="secondary">可拖拽节点并使用滚轮缩放；悬浮节点或连线可查看详情，下方表格提供完整数据。</Typography.Text>
      </Card>
      <Card title="拓扑节点"><Table className="nx-responsive-table" rowKey="id" columns={nodeColumns} dataSource={topology.nodes} pagination={false} tableLayout="fixed" /></Card>
      <Card title="拓扑关系"><Table className="nx-responsive-table" rowKey="id" columns={edgeColumns} dataSource={topology.edges} pagination={false} tableLayout="fixed" /></Card>
    </>}
    {data.selected_host_id && <NetworkChangeModal hostId={data.selected_host_id} kind={changeKind ?? "bridge"} open={changeKind !== null} onClose={() => setChangeKind(null)} />}
  </Space>;
}

const nodeColumns: ColumnsType<NetworkNode> = [
  { title: "名称", dataIndex: "label", render: (value: string, node) => <div><strong className="nx-technical">{value}</strong><small className="nx-mobile-table-detail">{nodeTypeInfo(node.node_type).label}</small></div> },
  { title: "类型", width: 150, responsive: ["md"], render: (_, node) => <TaggedText info={nodeTypeInfo(node.node_type)} /> },
  { title: "状态", dataIndex: "status", width: 120, responsive: ["md"], render: (value: string) => <NetworkStatusTag status={value} /> },
  { title: "标记", width: 260, responsive: ["lg"], render: (_, node) => <Space wrap>{node.management && <TaggedText info={managementInfo} tone="warning" />}{node.default_route && <TaggedText info={defaultRouteInfo} tone="running" />}{node.warnings.map((warning) => <TaggedText key={warning} info={warningInfo(warning)} tone="warning" />)}</Space> },
];

function NetworkStatusTag({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  if (normalized === "up") return <TaggedText info={{ label: "已连接", description: "接口已连接且正常转发" }} tone="running" />;
  if (normalized === "down") return <TaggedText info={{ label: "未连接", description: "接口处于 down 状态，不转发流量" }} tone="stopped" />;
  if (normalized === "unknown") return <TaggedText info={{ label: "状态未知", description: "接口状态无法识别" }} tone="unknown" />;
  return <TaggedText info={{ label: "需要关注", description: "接口状态异常，请结合告警判断" }} tone="warning" />;
}

const edgeColumns: ColumnsType<NetworkEdge> = [
  { title: "来源", dataIndex: "source", render: (value: string, edge) => <div><span className="nx-technical">{value}</span><small className="nx-mobile-table-detail">{relationInfo(edge.relation).label} → {edge.target}</small></div> },
  { title: "关系", width: 160, responsive: ["md"], render: (_, edge) => <TaggedText info={relationInfo(edge.relation)} /> },
  { title: "目标", dataIndex: "target", responsive: ["md"], render: (value: string) => <span className="nx-technical">{value}</span> },
  { title: "风险", dataIndex: "warnings", width: 240, responsive: ["lg"], render: (warnings: string[]) => <Space wrap>{warnings.map((warning) => <TaggedText key={warning} info={warningInfo(warning)} tone="warning" />)}</Space> },
];

function TaggedText({ info, tone }: { info: { label: string; description: string }; tone?: "running" | "warning" | "stopped" | "unknown" }) {
  const tag = <StatusTag label={info.label} tone={tone ?? "unknown"} />;
  if (!info.description) return tag;
  return <Tooltip title={info.description}><span>{tag}</span></Tooltip>;
}
