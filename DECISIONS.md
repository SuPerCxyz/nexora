# Architecture Decision Records

## ADR-001：FastAPI 服务端 Web

- 日期：2026-07-28
- 决定：FastAPI + Jinja2 + HTMX，少量局部 JavaScript。
- 原因：保持单体、轻量和渐进增强，避免 SPA 与常驻 Node 服务。

## ADR-002：Tabler UI

- 日期：2026-07-28
- 决定：统一使用 Tabler UI 和 Tabler Icons。
- 原因：提供一致、克制的管理界面，不混用图标和组件体系。

## ADR-003：SQLite 与单 worker

- 日期：2026-07-28
- 决定：SQLite/Alembic、WAL、单 Uvicorn worker、统一写入层。
- 放弃：外部数据库、多 worker 无协调写入。

## ADR-004：单容器内嵌任务

- 日期：2026-07-28
- 决定：Tini + Python 主进程 + 有限线程池 + SQLite lease。
- 放弃：Redis、Celery、RabbitMQ 和独立任务服务。

## ADR-005：无 Agent 管理

- 日期：2026-07-28
- 决定：SSH、远端标准工具、临时 stdin 脚本和按需 tunnel。
- 约束：不安装包、服务、cron、用户或永久脚本。

## ADR-006：远端 virsh 为首期 libvirt 主路径

- 日期：2026-07-28
- 决定：统一 RemoteExecutor 下执行远端 `virsh -c qemu:///system`。
- 原因：统一密码、私钥、sudo、Host Key、审计和错误语义。
- 影响：libvirt-python qemu+ssh 只在技术 Spike 和 ADR 后作为补充。

## ADR-007：节点作用域资源身份

- 日期：2026-07-28
- 决定：资源主身份为 `host_id + native_id`，数据库另用 opaque ID。
- 原因：迁移或复制后多个节点可能同时存在相同 UUID。

## ADR-008：平台媒体库

- 日期：2026-07-28
- 决定：ISO 使用受保护 Range 服务；系统镜像复制到目标节点。
- 放弃：通过 HTTP 直接运行系统盘、默认 backing-file 链接克隆。

## ADR-009：不修改 fstab

- 日期：2026-07-28
- 决定：NFS 只管理 netfs Pool 或纳管已有挂载目录。
- 约束：Pool 删除和节点移除不删除 NFS 业务内容。

## ADR-010：只支持关机迁移

- 日期：2026-07-28
- 决定：首期关闭 VM 后复制文件并在目标定义，默认保留源端。
- 放弃：在线迁移和复杂 block/network 磁盘迁移。

## ADR-011：单管理员

- 日期：2026-07-28
- 决定：首期仅一个本地管理员和内部 Session API。
- 放弃：多用户、RBAC、外部身份源和公共 API Token。

## ADR-012：安全网络写入

- 日期：2026-07-28
- 决定：管理链路写入必须有独立可靠的一次性回滚实体。
- 影响：缺少可靠调度能力的节点对管理链路保持只读。

## ADR-013：XML 局部保留修改

- 日期：2026-07-28
- 决定：安全解析后局部变更，区分 live/persistent hash。
- 放弃：字符串替换、正则修改和表单重建完整 XML。

