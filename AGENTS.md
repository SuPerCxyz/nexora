# Nexora Agent 开发规则

## 1. 指令优先级

1. 当前会话中用户的明确要求
2. 本文件
3. 仓库内权威产品、架构、安全和测试文档
4. 已启用 skill 的流程规则

发生冲突时停止实现，记录到 `PROJECT_STATUS.md`，由用户或 ADR 消除冲突。

## 2. 开始工作前

每次工作必须依次读取：

1. `PROJECT_STATUS.md`
2. `ROADMAP.md` 中当前任务
3. `ARCHITECTURE.md`
4. `DECISIONS.md`
5. `SECURITY.md`
6. `TEST_STATUS.md`
7. 与任务直接相关的 `docs/` 专题
8. `git status --short` 和最近提交（存在 Git 仓库时）

不得默认读取全部文档。先从文档索引定位最小充分上下文。

## 3. 不可突破的产品门禁

- 全新开发；不得复制 WebVirtCloud 或 Cockpit Machines 源码。
- 单容器、单 Uvicorn worker；SQLite 是唯一业务数据库。
- 不使用 Redis、Celery、外部数据库或外部任务队列。
- 管理容器不需要 KVM、不挂载 libvirt/docker socket、不使用 privileged。
- KVM 节点不得安装 Agent、守护进程、服务、cron、专用用户或数据库。
- 远端真实状态是虚拟化、存储、网络和设备资源的权威数据源。
- 不自动安装远端软件、写 sudoers、修改 `/etc/fstab` 或关闭安全机制。
- 所有危险写操作必须预检、生成 Diff、确认、验证并在必要时回滚。
- 网络写入没有可靠自动回滚能力时必须拒绝执行。
- 页面只使用内部 Session API；首期无公共 API、Token、多用户或 RBAC。

## 4. 架构硬约束

- 远端操作必须经过 `RemoteExecutor` 策略入口。
- 资源身份使用 `host_id + native_id`；不得把 UUID 当作跨节点全局主键。
- SSH Host Key 默认严格校验；变化时阻断连接，禁止自动覆盖。
- 凭据使用 AEAD 加密；主密钥不得进入数据库、日志、备份或文档。
- XML 禁用 DTD、外部实体、网络访问和 XInclude；禁止字符串或正则修改。
- SQLite 事务不得跨 SSH、文件复制、子进程或其他网络 I/O。
- 长任务使用持久化步骤、lease、heartbeat 和显式恢复策略。
- 所有时间以 UTC 存储，页面按管理员时区显示。

具体设计以 `ARCHITECTURE.md` 的专题链接为准。

## 5. 开发流程

- 轻量任务：明确目标、边界、风险和验证后直接实现。
- 新功能、行为变化和高风险修复：先设计，再计划，再实现。
- 真实 bug：先复现和定位根因，再修改。
- 公共 API、schema、shared types、根配置、CI、依赖或迁移变更必须先确认。
- 优先局部修改；不得顺手重构无关代码。
- 未经用户明确要求不得 commit、push、merge、rebase 或修改 Git 历史。
- 删除文件、业务数据或远端资源前必须获得明确确认。

## 6. 代码与测试

- Python 代码使用类型标注，遵循 Ruff 和项目现有风格。
- 安全边界、状态机、幂等、恢复、XML 和网络变更必须有自动化测试。
- 先运行定向测试；风险扩大时升级到相关回归测试。
- 没有命令和退出码证据，不得声称测试通过或任务完成。
- 关键验证不能执行时，必须写明原因并降低完成度表述。

## 7. 文档与交付

每次开发结束前必须更新：

- `PROJECT_STATUS.md`
- `ROADMAP.md`
- `TEST_STATUS.md`
- 必要的 `DECISIONS.md`、`SECURITY.md` 和 `CHANGELOG.md`

状态记录必须包含具体文件、测试命令、结果、未完成项和下一恢复入口。
禁止只写“后续继续”。新增约束应写入对应权威文档，不要扩张本文件。

