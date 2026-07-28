# Nexora 架构总览

## 架构目标

Nexora 是轻量级、无 Agent、单容器、多节点 libvirt/KVM Web 管理平台。
管理容器可运行在普通 Linux 节点，通过 SSH 管理已有 KVM/libvirt 节点。

## 系统边界

```text
Browser
  -> FastAPI + Jinja2 + HTMX
     -> SQLite data/task/audit layer
     -> embedded task coordinator
     -> RemoteExecutor
        -> SSH -> virsh/libvirt tools
        -> SFTP/SCP stream
        -> SSH console tunnel
```

远端节点保存并权威呈现虚拟机、网络、存储与设备状态。SQLite 只保存连接、
加密凭据、索引、缓存、标签、任务、操作和审计信息。

## 运行模型

- 单个业务容器，Tini 作为 PID 1。
- 单个 Uvicorn worker。
- Web、任务协调器、任务恢复器和连接管理器位于同一 Python 主进程。
- 有限线程池执行阻塞 SSH、libvirt 客户端和文件 I/O。
- websockify 与 SSH tunnel 按需创建，并由主进程跟踪和回收。
- SQLite 启用 WAL、foreign keys、busy timeout、checkpoint 和完整性检查。
- 数据库迁移成功后才进入 ready 状态。

## 模块边界

- `web`：页面、HTMX 和内部 API，不承载关键后台工作。
- `auth`：单管理员、Session、CSRF、登录限速和安全设置。
- `remote`：SSH、Host Key、命令适配器、文件传输和隧道。
- `inventory`：只读探测、资源规范化、索引和带外变更检测。
- `virtualization`：Domain XML、生命周期、设备和控制台。
- `storage`：dir/netfs Pool、卷、镜像复制和引用检查。
- `networking`：只读发现、Bridge/VLAN 计划、应用和回滚。
- `media`：受限目录扫描、索引、Range 服务和凭据。
- `tasks`：持久化任务、步骤、锁、lease、恢复和取消。
- `audit`：不可变安全与操作事件。

## 权威专题

- 产品边界：`docs/product/REQUIREMENTS.md`
- 阶段与非目标：`docs/product/SCOPE.md`
- 远端管理：`docs/architecture/REMOTE_MANAGEMENT.md`
- 任务系统：`docs/architecture/TASK_SYSTEM.md`
- 资源同步与 XML：`docs/architecture/RESOURCE_SYNC_XML.md`
- 媒体与存储：`docs/architecture/MEDIA_STORAGE.md`
- 网络安全变更：`docs/architecture/NETWORKING.md`
- 运行与部署：`docs/architecture/RUNTIME_DEPLOYMENT.md`
- 控制台与迁移：`docs/architecture/CONSOLE_MIGRATION.md`
- 页面系统：`docs/architecture/FRONTEND.md`

## 关键不变量

1. 远端写入前重新读取真实状态。
2. 写入携带 base generation/hash，冲突时拒绝覆盖。
3. 原生资源身份始终处于 `host_id` 作用域。
4. 任务数据库事务不跨远端 I/O。
5. 未知资源和未知 XML 必须保留并可见。
6. 节点移除不删除任何业务资源。

