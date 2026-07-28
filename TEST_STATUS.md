# Nexora 测试状态

## 当前状态

- 当前阶段：文档与架构基线
- 已实现代码：无
- 自动化测试：尚未建立
- 集成环境：尚未建立
- 最近验证：文档结构、关键决策一致性和状态必填章节检查

## 已执行验证

| 日期 | 命令 | 结果 | 范围 |
|---|---|---|---|
| 2026-07-28 | 必需文件、行数、章节和尾随空白综合检查 | PASS；22 个文档，最大 90 行 | 文档结构 |
| 2026-07-28 | 必需文件 shell 存在性检查 | PASS；8 个根目录必需文件齐全 | 文档结构 |
| 2026-07-28 | `rg` 检查身份、RemoteExecutor、lease、回滚决策 | PASS；关键约束口径一致 | 架构一致性 |
| 2026-07-28 | shell 检查 `PROJECT_STATUS.md` 16 个章节 | PASS；章节齐全 | 恢复状态 |
| 2026-07-28 | `git status --short` | EXPECTED FAIL；目录尚非 Git 仓库 | Git 状态 |

## 计划中的单元测试

- SSH argv 编码、Host Key、凭据加密和脱敏。
- XML 安全解析、生成、未知元素保留、规范化和 Diff。
- CPU topology、NUMA、HugePages、磁盘、网卡和 PCI 判断。
- 媒体路径、HTTP Range、token、SHA-256 和镜像复制恢复。
- Pool、NFS netfs、Bridge、VLAN 与网络后端探测。
- 网络计划、独立回滚、确认超时和恢复。
- 任务原子领取、lease、锁、取消、幂等和崩溃恢复。
- 资源复合身份、generation/hash 和带外冲突。

## 计划中的集成测试

- 单容器且无 `/dev/kvm`、无 libvirt socket、非 privileged。
- 首次管理员初始化、登录、改密和 Session 撤销。
- root/普通用户免密 sudo，密码/私钥 SSH，Host Key 变化。
- 传统及模块化 libvirt，两台远端 KVM 节点。
- 已有 VM/Pool/网络/Bridge/VLAN 自动发现。
- Linux/Windows VM、ISO、镜像复制、noVNC、串口、快照和克隆。
- NetworkManager、networkd、Netplan、网络失联自动回滚。
- dir/NFS netfs、关机迁移、容器重启任务恢复。

## 故障注入与零残留

覆盖 SSH/节点/容器中断、SQLite 锁、复制中断、哈希不符、XML 失败、重复提交、
并发 VM 修改、Tunnel 中断和媒体吊销。

节点移除后检查进程、unit、cron、临时目录、socket、连接和系统路径，不得存在
Nexora 临时实体；VM、磁盘、Pool、NFS、Bridge 和 VLAN 必须仍存在。

## 未验证项

全部运行时代码、容器、远端集成和性能指标均未实现，因此均未验证。
