# VM 创建本地 ISO 设计

## 范围

managed Volume 导入创建时可选挂载同节点本地 ISO。只接受 active dir/netfs Pool 中
已索引的 managed raw `.iso` Volume；不接受页面路径、不扫描目录、不复制或删除 ISO。

平台 `/library` ISO 需要 HTTP 能力判定或缓存复制长任务，保留为后续独立创建流程，
不得隐式混入 Domain define。

## 权威与并发

预览和执行复用 Storage 全量刷新，并复核：

- ISO ResourceIndex 与 VM 目标节点一致。
- native ID、generation/hash、Volume Key 和名称未变化。
- 父 Pool 为 active managed dir/netfs。
- 格式为 raw，权威绝对路径以 `.iso` 结尾。

ISO 允许多个 VM readonly 共享。任务按 native ID 排序锁定系统盘与 ISO Volume，再锁
目标 VM UUID，避免并发任务反向取得双 Volume 锁。

## XML 与恢复

生成 readonly SATA CD-ROM，target 为 `sda`，系统盘为 `vda`。选择 ISO 时启动顺序为
CD-ROM 1、Disk 2；未选择时 Disk 1。路径只来自权威索引。

写后验证 CD-ROM 的 device/type/source/bus/readonly。恢复为 verify_only，只有系统盘
和 CD-ROM 均匹配计划才成功；失败不弹出、不修改或删除 ISO。

## 验收

- 单元：无 ISO、合法 ISO、非 raw、非绝对路径、跨节点和 hash 变化。
- Web：只显示同节点候选，不存在路径字段。
- Rocky：创建专用 ISO 与系统盘，经 Nexora 定义 VM，验证 readonly SATA CD-ROM、
  启动和 ISO 保留，再精确清理测试 VM、系统盘与 ISO。
