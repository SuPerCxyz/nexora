# SQLite 持久化任务系统

## 原则

关键长任务不得使用 FastAPI `BackgroundTasks`。任务、步骤、检查点、心跳和恢复
状态持久化到 SQLite，并由单个进程内协调器领取。

## 状态

`pending`、`queued`、`running`、`waiting_confirmation`、`cancel_requested`、
`cancelled`、`succeeded`、`failed`、`timed_out`、`interrupted`、`recovering`、
`unknown`。

## 任务与步骤

Task 至少保存类型、目标、operation ID、幂等键、状态、进度、当前步骤、摘要、
错误、时间、取消、重试、可恢复性、恢复策略、检查点和父任务。

TaskStep 保存顺序、状态、时间、尝试次数、脱敏命令摘要、输出摘要、错误、
检查点版本和补偿状态。每完成一步立即提交短事务。

## 原子领取与 lease

- 使用短事务和条件更新原子领取 pending/queued 任务。
- 领取后写入 `lease_owner`、`lease_expires_at` 和 `heartbeat_at`。
- worker 定期续租；lease 过期不等于可以盲目重跑。
- SQLite 事务不得跨 SSH、文件复制、子进程或等待确认。
- 所有时间以 UTC 保存；恢复判断保留时钟跳变宽限。
- 幂等键的唯一范围为 `task_type + target scope + idempotency_key`。

## 恢复

启动时扫描非终态任务，先执行外部状态验证，再选择：

- `verify_only`
- `resume_from_checkpoint`
- `rollback`
- `retry_from_start`
- `manual_intervention`

文件、VM、网络和存储任务分别提供恢复适配器。未知结果进入 `unknown` 或人工干预，
不得以“最后步骤未提交”为由重复执行危险动作。

## 取消与关闭

- 取消为协作式：设置标记，worker 在安全检查点退出。
- 不得在线程正执行不可中断写入时伪造已取消。
- 容器关闭先停止领取，再通知运行任务，在宽限期内写入检查点。
- 关闭超时的任务标记为 `interrupted`，下次启动验证外部状态。

## 并发与锁

- 同一 VM、磁盘危险操作和节点网络写入串行。
- 每节点最多一个网络 Apply。
- 查询、文件复制、SSH、控制台和全局任务分别配置并发上限。
- 资源锁使用有期限 lease；进程内锁只作优化，不是唯一正确性保障。
- 锁顺序固定，避免 VM、存储和主机锁死锁。

## 保留与可观测性

任务中心展示步骤、心跳、脱敏输出、错误、复制速度和恢复建议。
输出设置单条和总量上限；任务、命令输出、审计与性能数据使用独立保留策略。

