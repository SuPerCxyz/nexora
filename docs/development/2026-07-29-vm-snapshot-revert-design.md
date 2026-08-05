# VM Snapshot 最小安全恢复设计

## 目标与选择

首期恢复只允许“配置等价的 current internal leaf”。比较方案：

1. 任意历史点恢复：会切换 Snapshot 分支并可能回退 Domain 配置，暂不采用。
2. current leaf 且配置等价：只回退快照后的磁盘写入，采用。
3. 保持只读：风险最低但不满足 Cockpit Machines 基线。

用户已要求自动持续推进，因此在不扩大上述边界的前提下直接实施。

## 权威门禁

预览和执行前必须重新读取 VM、完整 Snapshot 集合及目标 XML，并要求：

- VM persistent、shutoff，全部 writable disk 为绝对路径 file/qcow2。
- 目标 managed，resource ID/native ID/hash 与提交基线一致。
- 目标是 current 且没有子 Snapshot。
- Snapshot state 为 shutoff、memory=no，磁盘模式仅 internal/no 且至少一个 internal。
- Snapshot XML 必须包含 `<domain>`，其安全规范化 hash 等于当前 persistent Domain hash。
- 不使用 `--force`、`--running`、`--paused` 或 `--reset-nvram`。

以上限制保证 Nexora 不切换分支、不恢复内存、不改变启动状态，也不静默回退
CPU、内存、设备、NVRAM 或其他 Domain 配置。

## 计划与任务

复用 revision 0013 `snapshot_change_plans`，operation 为 `revert`，保存 VM 与
Snapshot 双基线、配置等价摘要、Diff 和限时确认 digest。页面要求再次输入 VM 名称。

三步持久化任务：

1. 刷新 VM/Snapshot，复核 current leaf、磁盘模式及 Domain hash 等价。
2. 执行 `virsh snapshot-revert <uuid> <name>`。
3. 重新发现并验证目标仍是 current、VM 仍 shutoff、persistent XML hash 不变。

任务持有 VM 与 Snapshot 双锁，恢复策略为 `verify_only`。命令或验证结果不明确时
禁止自动重放、强制恢复或删除任何 Snapshot。

## 测试

- 单元覆盖非 current、非 leaf、memory、external、配置 hash 不同和确认 scope。
- 任务覆盖三步进度、双锁、禁止危险 flags 和最终权威验证。
- Rocky 集成使用 `qemu-io`：快照前写入模式 A，快照后写入模式 B，Nexora 恢复后
  读取并验证模式 A；随后精确删除 Snapshot、VM 和磁盘。
