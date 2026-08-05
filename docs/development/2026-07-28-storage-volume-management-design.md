# Storage Volume 管理设计

## 目标

在已发现的 writable dir/netfs Pool 中管理 qcow2/raw Volume。远端 libvirt 是权威
数据源，Volume 身份固定为 `host_id + Pool UUID + Volume Key`。

## 支持范围

- 创建 qcow2/raw Volume，不覆盖同名 Volume 或目标文件。
- 仅扩容，不允许 shrink；活跃 VM 引用时拒绝离线扩容。
- 显式删除未被任何 VM 引用的 Volume。
- 刷新后展示已有 Volume；其他 Pool/格式保持只读。

首期不处理外部 snapshot chain、block/RBD/iSCSI 删除或在线 blockresize。

## 确认计划

`StorageVolumeChangePlan` 持久化 host、Pool UUID、Volume Key/name、operation、Pool 与
Volume base generation/hash、当前/目标 XML、Diff、结构化输入、确认摘要、过期时间
和结果。

创建计划先生成安全 Volume XML，并通过远端 `virt-xml-validate - storagevol`。
扩容和删除计划保存当前 Volume XML；删除 Diff 指向 `/dev/null`。

## 写入门禁

1. 权威刷新 Pool、Volume 和 Domain。
2. 验证 Pool 为 managed dir/netfs 且 active。
3. 验证 Pool generation/hash 与页面基线一致。
4. 创建时阻断同名 Volume、Key 或目标路径。
5. 扩容/删除时按 file path 与 `<source pool volume>` 阻断 VM 引用。
6. 获取 `host + storage_volume + native_id` 资源租约。
7. 再次执行全部预检后才调用 virsh。
8. 写后重新读取并验证 Key、格式、容量和最终状态。

数据库事务不得跨 SSH 或文件 I/O。

## 命令与恢复

- 创建：`virsh vol-create <pool-uuid> /dev/stdin --validate`。
- 扩容：`virsh vol-resize <volume-key> <bytes> <pool-uuid>`，不传 `--shrink`。
- 删除：`virsh vol-delete <volume-key> <pool-uuid>`，不传 `--delete-snapshots`。

创建中断可按计划 name/Key 查询：完全匹配则成功，不存在则显式重试，不一致则冲突。
扩容中断只验证容量，不自动再次扩大。删除中断只验证 Volume 是否仍存在；不得盲目
重放不可逆删除。

## 删除与回滚

删除页面逐项显示完整 Key、路径、Pool、格式、容量和 VM 引用结果。删除不可自动
恢复，因此必须二次确认且任务不自动重试。创建失败只可删除本计划成功创建且仍无
引用的 Volume；扩容失败进入人工验证，不尝试 shrink 回滚。

## 测试

- XML、安全名称/容量、身份编码、确认过期与带外冲突。
- 同名无覆盖、VM file/volume 引用、活跃 VM 扩容阻断。
- 创建中断幂等、扩容 verify-only、删除不可重放。
- Rocky dir 与回环 NFS Pool 的 qcow2/raw 创建、扩容、删除和文件保留边界。

## 实现结果

2026-07-29 完成 revision 0012 纵向切片。创建任务允许按计划幂等恢复；扩容与删除
任务采用 `verify_only`，不自动重放。扩容同时获取 Pool 与 Volume 资源锁，写后用
预期 XML hash 接纳平台内变更。

真实 libvirt 会动态更新 Volume XML 的 allocation、physical 与 timestamps。它们
保留在详情和原始 XML 中，但从持久配置 hash 排除，避免容量统计变化被误报为带外
配置修改；capacity、format、path/key、permissions 等仍参与冲突检测。

Rocky 9.7 的 dir 和回环 NFSv3 netfs Pool 均通过 qcow2 创建、8 MiB 到 16 MiB
扩容、显式删除和远端零残留复核。
