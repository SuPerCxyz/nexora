# VM Snapshot 安全删除设计

## 目标与方案选择

在已完成 internal Snapshot 创建后，增加最小可验证的删除能力。比较方案：

1. 仅删除无子节点的 internal leaf：风险边界明确，推荐并采用。
2. 同时支持 children/children-only：一次改变多条磁盘链，失败状态难证明，拒绝。
3. 仅删除 metadata：保留不可见磁盘内容，容易制造孤立状态，拒绝作为产品删除。

恢复 Snapshot 会回退客户机数据并可能替换 Domain 配置，必须另行设计，不进入本切片。

## 权威元数据

Snapshot XML 解析增加：

- `<parent><name>` 对应 `parent_name`。
- 当前指针由 `virsh snapshot-current <uuid> --name` 读取并保存为 `current`。

发现时若 Snapshot 集合非空但 current 查询失败，整次扫描失败，禁止用不完整拓扑执行
写操作。页面继续展示所有已发现 Snapshot，包括不支持删除的项。

## 删除门禁

预览与执行前均重新扫描 Domain 和完整 Snapshot 集合，并要求：

- VM persistent 且 shutoff。
- VM 所有 writable disk 均为绝对路径 file/qcow2。
- 目标 Snapshot 状态 managed，generation/hash 与页面基线一致。
- memory=no，所有磁盘模式仅为 internal/no，且至少一个 internal。
- 没有其他 Snapshot 的 `parent_name` 指向目标。
- 不使用 `--children`、`--children-only` 或 `--metadata`。

删除 current leaf 被允许；libvirt 将权威 current 指针调整到父 Snapshot 或无 current。

## 持久化任务

复用 revision 0013 的独立 `snapshot_change_plans`，operation 为 `delete`，同时保存 VM
与 Snapshot 双基线。确认 token 绑定 plan、host、VM UUID 和 Snapshot name。

三步任务：

1. 刷新 VM/Snapshot 并复核 leaf、hash 与磁盘模式。
2. 执行 `virsh snapshot-delete <uuid> <name>`。
3. 重新扫描，要求目标 missing，其他 Snapshot 的 generation/hash 未意外变化，
   VM persistent XML hash 不变。

任务持有 VM 与 Snapshot 双租约锁，恢复策略为 `verify_only`。命令或验证失败时不得
自动重试、恢复或删除其他元数据；管理员必须重新扫描后决定。

## 测试与验收

- 单元：parent/current 解析、非 leaf/外部/内存/带外 hash 阻断、确认 scope。
- 任务：三步进度、双锁、目标 missing、VM XML 不变。
- 真实 Rocky：创建 parent+leaf，Nexora 删除 leaf，parent 保留且磁盘可由 QEMU 读取。
- 清理：专用 Snapshot、VM 定义和磁盘全部精确删除，不影响既有测试资源。
