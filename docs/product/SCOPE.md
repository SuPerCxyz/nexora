# 产品范围与实施阶段

## 首期宿主机与客户机

- 宿主机：Linux KVM/libvirt；主要兼容 Ubuntu、Debian、Rocky、AlmaLinux、
  RHEL 和 openEuler。
- 架构：x86_64、aarch64。
- 客户机：Linux、Windows。
- 兼容传统 libvirtd 与模块化 libvirt daemon。

## P0 基础架构

- 项目骨架、单容器、SQLite/Alembic、认证与 Session。
- RemoteExecutor、凭据加密、Host Key 和持久化任务系统。
- 浅色 Tabler 基础布局、开发文档和测试框架。

## P1 节点与存量资源

- 添加/移除节点、能力探测、资源扫描和索引。
- VM、Pool、libvirt 网络、宿主网络和设备纳管。
- 带外变更检测与节点移除零残留。

## P2 Cockpit Machines 基线

- 创建和生命周期、CPU、内存、磁盘、网卡。
- 控制台、串口、快照、克隆、Host Device、固件和 TPM。
- watchdog、vsock、共享目录、性能统计和 libvirt 网络。

## P3 媒体与存储

- 媒体索引、HTTP Range、ISO 远程挂载及缓存回退。
- 镜像复制、dir Pool、NFS netfs Pool 和文件任务恢复。

## P4 宿主机网络

- 后端探测、拓扑、Linux Bridge、VLAN。
- 配置 Diff、风险评估、自动回滚和管理 IP 迁移。

## P5 高级配置与迁移

- CPU Pinning、NUMA、HugePages、高级磁盘/网卡、PCI/USB。
- 高级固件、未知 XML 保留、关机迁移和磁盘同步。

## P6 产品化

- 多发行版与 aarch64 验证、安全审计、性能和可访问性。
- 备份恢复、升级回滚、排障、供应链和发布文档。

## 首期明确不实现

- 多用户、RBAC、多租户、LDAP/OIDC/SAML。
- 公共 API、外部 API Token、公共 API 稳定性承诺。
- HA、自动调度、疏散、负载均衡和在线迁移。
- Ceph/iSCSI/FC 管理、LVM Pool 创建。
- Bond/OVS 写操作、VXLAN、EVPN、SDN、防火墙和安全组管理。
- 增量备份平台、vGPU 完整管理、Kubernetes。
- 宿主机升级、用户管理、服务管理和 `/etc/fstab` 修改。

上述现有资源应尽可能发现并以只读或部分支持状态展示。

## 首批最小可验证功能

1. 单容器启动、首次管理员初始化、登录和退出。
2. SSH 添加节点、Host Key 确认、libvirt/CPU/内存/VM 读取。
3. 自动展示已有虚拟机，无需导入。
4. 持久化任务步骤和进度，重启后识别中断任务。
5. 扫描 `/library` 中 ISO、qcow2 和 raw。
6. CPU 结构化修改、XML Diff 和未知元素保留测试。
7. 只读展示物理接口、Bridge、VLAN 与 VM 网卡拓扑。

