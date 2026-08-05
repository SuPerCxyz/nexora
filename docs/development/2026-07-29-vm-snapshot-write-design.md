# VM Snapshot 写操作设计

## 首个写切片

创建 libvirt internal disk Snapshot：

- VM 必须 persistent 且已关闭。
- 至少一个 writable disk，全部 writable disk 必须是 file/qcow2。
- CD-ROM、readonly 磁盘和无 source 设备不参与限制。
- Snapshot 名称使用安全 ASCII 标识，description 有长度和控制字符限制。
- 不创建内存 Snapshot，不使用 external overlay，不修改 backing chain。
- 使用 `virsh snapshot-create-as <uuid> <name> <description> --atomic`。

## 持久化确认

revision 0013 新增 `snapshot_change_plans`，保存 VM 与 Snapshot 双基线、操作输入、
预检查摘要、确认 digest、状态和时间。预览、确认、任务执行之间重新读取远端 VM
和完整 Snapshot 集合，发现带外变化即阻断。

任务持有 VM 与 `domain_uuid + snapshot_name` 两把租约锁，分三步执行：

1. 刷新 VM/Snapshot 权威状态并复核基线。
2. 原子创建 internal Snapshot。
3. 重新发现并验证 Snapshot XML、memory=no 和所有磁盘为 internal。

命令成功但验证失败时不自动删除 Snapshot，避免把已完成的存储操作误回滚；任务标记
失败并要求人工复核。恢复策略为 `verify_only`，容器重启后不得盲目重放。

## 后续扩展

删除只允许 memory=no 且全 internal 的 Snapshot。恢复还必须验证 snapshot XML 中
Domain 配置、目标状态和写后 VM hash，单独设计，不使用 `--force`。external、
raw、block/network disk 和复杂链保持只读。
