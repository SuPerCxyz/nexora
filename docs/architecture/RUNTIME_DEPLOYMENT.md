# 单容器运行与部署

## 容器约束

Compose 只包含 `nexora` 一个业务服务。禁止 privileged 以及默认挂载：

- `/dev/kvm`
- libvirt socket
- Docker socket

容器不得启动 libvirtd、virtqemud、QEMU、NetworkManager 或 systemd-networkd。
运行镜像不包含 Node.js 服务；前端资产在构建阶段生成并本地提供。

## 进程生命周期

- Tini 为 PID 1，Python 主进程接收信号。
- 单 Uvicorn worker；生产禁止 reload。
- 主进程拥有任务协调器、恢复器、连接池、线程池和所有子进程句柄。
- 子进程创建独立进程组并有明确关闭宽限期。
- 退出顺序：停止接流量、停止领取任务、保存检查点、关闭隧道/代理、关闭数据库。

## 持久化

所有状态在 `/data`：

```text
database credentials hostkeys logs tasks task-output operations audit
console runtime backups progress cache recovery
```

媒体只从 `/library` 读取。容器重建并重新挂载 `/data`、`/library` 后，应恢复管理员、
节点、凭据密文、任务、审计、索引、设置和操作历史。

## 健康检查

- `/live`：主进程能够响应。
- `/ready`：数据目录可写、密钥有效、迁移完成、SQLite 可用、协调器已启动。

迁移失败、缺少凭据主密钥、数据库损坏或 `/data` 不可写时 fail closed，不进入 ready。
磁盘空间低于安全阈值时拒绝新增长任务和大文件任务，并发出告警。

## SQLite

启用 WAL、foreign keys、busy timeout、定期 checkpoint、integrity check 和自动备份。
限制写并发，每个线程使用独立 SQLAlchemy Session。连接/事务不得跨线程共享。

## 发布与供应链

- 容器以非 root 用户运行，最小 capabilities。
- 多阶段构建，不把编译工具留在运行镜像。
- Python/前端依赖锁定；基础镜像固定版本，发布时建议固定 digest。
- 生成 SBOM 和第三方许可证清单，执行镜像漏洞扫描。
- 静态资源不依赖公网 CDN。

## 备份、恢复与回滚

备份包含 SQLite 一致性快照和恢复所需元数据，但不包含环境注入的主密钥。
恢复必须同时提供原凭据密钥。升级前创建新备份且不覆盖旧备份。

数据库 downgrade 未经逐迁移验证不得承诺；默认回滚方式是恢复升级前备份和兼容镜像。

