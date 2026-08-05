# 节点能力与硬件详情设计

## 目标

节点详情面向平台管理员展示可理解的功能支持状态和硬件摘要，不再直接暴露内部
capability key、命令路径或原始 JSON。

## 边界

- 保留现有节点接入、扫描、任务、SSH、审计和资源发现流程。
- 继续通过 `RemoteExecutor` 执行固定只读命令。
- 复用 `HostCapability` 与 `ResourceIndex`，不新增数据库表或迁移。
- 支持当前 x86_64 Rocky、Debian、Ubuntu 边界；aarch64 和其他 RHEL 系暂缓。
- 不采集主机序列号、磁盘序列号或其他硬件唯一标识。

## 数据采集

能力探测新增 `lscpu -J`，并读取固定 DMI sysfs 文件中的厂商和产品型号。命令失败
时局部标记未知，不影响其他能力结果。已有 `virsh nodeinfo` 作为 CPU、内存和 NUMA
的降级来源。

网卡信息复用最近一次宿主接口资源扫描，展示名称、MAC、类型、链路状态及管理链路
标记。默认排除 loopback、veth、vnet 和 tap，仅保留实体接口与管理链路。

## 接口与页面

内部节点详情 API 增加：

- `hardware`：系统、CPU、内存和 NUMA 摘要。
- `network_adapters`：筛选后的网卡摘要。
- `features`：用户功能名称、支持状态和简短说明。

页面顺序为节点摘要、硬件概览、网卡信息、功能支持、子系统状态、虚拟机。功能状态
只使用“支持”“不支持”“需关注”，并沿用统一浅亮无边框状态 Tag。

## 安全与失败处理

DMI 只读取厂商和产品名称，不读取 serial、UUID 或 asset tag。所有输出继续受现有
RemoteExecutor 超时和大小限制。单项硬件探测失败时显示“暂未获取”，不阻断节点
资源查看或扫描。

## 验证

- parser、功能映射、网卡筛选和 API contract 单元测试。
- React 节点详情测试及 1280/375px Browser QA。
- Rocky 真实节点重新扫描，复核 CPU、内存、网卡 MAC 和功能状态。
- 全量 lint、typecheck、test、build 与容器安全验证。
