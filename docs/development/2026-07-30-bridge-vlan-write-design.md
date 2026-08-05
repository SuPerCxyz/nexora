# P4-002 Bridge/VLAN 安全写入设计

## 目标

在只读网络拓扑（P4-001）基础上，支持 Linux Bridge 和 VLAN 的安全写入操作，
包含独立回滚、确认期限和管理 IP 迁移。

## 范围

### 实现

- 创建/删除 Linux Bridge
- 创建/删除 VLAN 子接口
- 将物理口加入/移出 Bridge
- 管理口 IP 迁移到 Bridge
- 自动回滚与确认期限

### 不实现

- Bond、OVS、VXLAN、EVPN、SDN
- 防火墙和安全组管理
- NetworkManager 写操作（只读发现 NetworkManager，写入使用 ip 命令）

## 安全模型

### 核心原则

1. **管理连通性优先**：任何网络写入操作不得断开管理 SSH 连接
2. **独立回滚**：每个操作有独立的回滚脚本，不依赖外部状态
3. **确认期限**：写入后需在确认期限内验证连通性，超时自动回滚
4. **最小权限**：只使用 sudo ip 命令，不修改持久化配置文件

### 回滚策略

```
预检 -> 生成回滚脚本 -> 执行写入 -> 等待确认 -> 确认/超时回滚
```

- 预检：验证目标接口存在、不冲突、管理口不在受影响范围
- 回滚脚本：在执行前生成，包含完整的逆操作
- 确认期限：默认 60 秒，可通过配置调整
- 超时回滚：通过持久化任务和 heartbeat 实现

### 管理口保护

- 预检阶段识别管理 SSH 源接口
- 禁止直接修改管理口配置
- IP 迁移到 Bridge 时，先创建 Bridge 再迁移，确保 SSH 不断
- 回滚脚本优先恢复管理口

## 技术方案

### 命令层

使用 `ip` 命令族，不修改 `/etc/network/interfaces`、Netplan 或 NetworkManager 配置：

- `ip link add name <bridge> type bridge`
- `ip link set dev <iface> master <bridge>`
- `ip link add link <iface> name <iface>.<vlan> type vlan id <vlan>`
- `ip addr add <cidr> dev <bridge>`

### 数据模型

复用现有 VmChangePlan 模式：

- `NetworkChangePlan`：持久化预览、确认、回滚脚本
- `change_type`：`bridge_create`、`bridge_delete`、`vlan_create`、`vlan_delete`、`port_attach`、`port_detach`、`ip_migrate`
- `rollback_script`：预生成的逆操作 shell 脚本
- `confirmation_deadline`：超时自动回滚时间戳

### 任务流程

1. **Preview**：预检 + 生成 Diff + 生成回滚脚本 + 持久化计划
2. **Confirm**：用户确认 + 创建持久化任务
3. **Execute**：
   - 步骤 1：执行写入
   - 步骤 2：等待确认（heartbeat）
   - 步骤 3：用户确认 -> 标记成功 / 超时 -> 执行回滚脚本
4. **Verify**：刷新网络拓扑，验证结果

### 前端

- 网络拓扑页增加"创建 Bridge"、"创建 VLAN"按钮
- 操作前显示预检结果和 Diff
- 确认页面显示回滚脚本和超时倒计时
- 超时后自动跳转到回滚结果

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| SSH 断连 | 管理口保护 + 自动回滚 + 确认期限 |
| 持久化丢失 | ip 命令不修改持久化配置；重启后恢复原状态 |
| 并发冲突 | ResourceLockStore 接口级锁 |
| 命令注入 | 结构化输入 + 白名单校验 + 不拼接 shell |

## 依赖

- 无 schema 变更（复用 VmChangePlan 或新增 NetworkChangePlan 表）
- 无新增依赖
- 需要 sudo ip 权限

## 验收条件

- Bridge 创建/删除通过真实 Rocky 验证
- VLAN 创建/删除通过真实 Rocky 验证
- 管理口迁移并自动回滚通过真实验证
- 确认期限超时自动回滚通过测试
- 零残留：操作后网络配置可完全恢复
