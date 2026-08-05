# 宿主机网络只读拓扑实现记录

## 数据边界

页面只读取现有 Host 与 ResourceIndex，不在 GET 请求中发起 SSH、资源扫描或任务。
Host Interface 的 ifindex 是接口节点身份；VM 使用 host-scoped libvirt UUID，
VM NIC 使用 VM UUID 与接口序号。missing 资源不进入当前拓扑。

接口发现固定使用只读 `ip -d -j link show`，保留 Bridge、VLAN、tun/tap 等详细
类型信息；解析器不得把 libvirt `vnet`/tap 因内核 `tun` kind 而降级为物理接口。

## 关系

- VLAN parent：parent interface → VLAN。
- Bridge port：物理口/VLAN → Bridge；Bridge → tap/vnet。
- VM attachment：tap/vnet（或无 target 时的 source Bridge）→ VM NIC → VM。

管理 IP 从 Host 管理地址与接口地址精确匹配，随后只沿 parent/bridge_port 关系传播。
默认路由、link down、无 Carrier 与相邻接口 MTU 不一致均以文字标记，不只依赖颜色。

## 安全与上限

最多读取 20,000 个相关资源、每台 VM 最多 256 个接口。details_json 必须是对象，
ifindex 必须为正整数；无效资源使当前页面明确失败，不猜测或拼接任意标识。

## 页面

`/networks` 提供节点选择、摘要、节点表与关系表，作为无 JavaScript 可访问回退。
Cytoscape 图形层复用同一不可变拓扑模型；由于新增 npm/lockfile 依赖需要确认，
当前先保留回退页面并记录到集中待确认清单。

## 验证

单元覆盖完整物理口/VLAN/Bridge/vnet/VM 链、管理链路、默认路由、MTU 与 Carrier。
真实 Rocky 验证物理口、Bridge、vnet、管理链和默认路由；节点没有 active Bridge
时不得伪造。Web 验证页面读取不创建 Task，并覆盖认证、404、桌面与 375px 响应式。
