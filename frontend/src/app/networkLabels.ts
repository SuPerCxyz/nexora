export type LabelInfo = { label: string; description: string };

import { designTokens } from "./designTokens";

export const nodeTypeColor: Record<string, string> = {
  physical: designTokens.success,
  vlan: designTokens.special,
  bridge: designTokens.info,
  vnet: designTokens.warning,
  tap: designTokens.neutral400,
  veth: designTokens.textTertiary,
  vm_nic: designTokens.primary,
  virtual_machine: designTokens.textSecondary,
  unknown: designTokens.neutral,
};

export const nodeTypeLabels: Record<string, LabelInfo> = {
  physical: { label: "物理网卡", description: "宿主机物理以太网口，承载最终二层转发" },
  vlan: { label: "VLAN 子接口", description: "基于下层物理网卡的 802.1Q VLAN 子接口" },
  bridge: { label: "网桥", description: "Linux 网桥，聚合多个端口并转发二层流量" },
  vnet: { label: "虚拟机接口", description: "libvirt 为运行中虚拟机创建的宿主侧虚拟接口" },
  tap: { label: "TAP 接口", description: "TAP 虚拟设备，供虚拟机或程序收发数据包" },
  veth: { label: "容器接口", description: "虚拟以太网对，通常来自容器网络" },
  vm_nic: { label: "虚拟机网卡", description: "虚拟机内部的网络设备；透传网卡展示 PCI 地址与设备名" },
  virtual_machine: { label: "虚拟机", description: "KVM 虚拟机" },
  unknown: { label: "未知接口", description: "无法识别的接口类型" },
};

export const relationLabels: Record<string, LabelInfo> = {
  parent: { label: "父接口", description: "此接口基于下方的物理/父接口创建" },
  bridge_port: { label: "桥接端口", description: "此接口是上方网桥的一个端口" },
  vm_attachment: { label: "VM 挂载", description: "虚拟机网卡挂载到该接口" },
  belongs_to: { label: "属于", description: "该网卡属于对应的虚拟机" },
};

export const warningLabels: Record<string, LabelInfo> = {
  link_down: { label: "链路断开", description: "接口状态为 down / lower-layer-down，当前不转发流量" },
  no_carrier: { label: "无载波", description: "物理接口未检测到网线或光信号，可能未接线或对端未启动" },
  mtu_mismatch: { label: "MTU 不一致", description: "两端 MTU 值不同，大报文可能被丢弃" },
};

export const managementInfo: LabelInfo = {
  label: "管理链路",
  description: "该接口承载节点的管理地址或默认路由，修改可能导致管理连接中断",
};

export const defaultRouteInfo: LabelInfo = {
  label: "默认路由",
  description: "该接口承载节点的默认路由",
};

export function nodeTypeInfo(nodeType: string): LabelInfo {
  return nodeTypeLabels[nodeType] ?? { label: nodeType, description: "未知的节点类型" };
}

export function relationInfo(relation: string): LabelInfo {
  return relationLabels[relation] ?? { label: relation, description: "未知的关系类型" };
}

export function warningInfo(warning: string): LabelInfo {
  return warningLabels[warning] ?? { label: warning, description: "接口存在异常，请结合状态判断" };
}
