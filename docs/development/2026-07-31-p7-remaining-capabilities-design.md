# P7 剩余首期能力设计

## 目标与边界

补齐 24h VM 指标与节点性能、Watchdog/vsock/CPU cache tuning 写入、关机 VM
PCI/USB 直通、virtiofs/9p 共享目录和 Cloud Image 静态 IPv6。暂不做 aarch64、
Rocky 之外 RHEL 系、在线迁移、任意历史分支恢复、复杂 Snapshot 链或高级网络写入。

## 分阶段交付

1. P7-001 接通已有 VM 指标历史 store，新增节点采样、保留、查询和页面。
2. P7-002 复用 VM XML 计划实现 Watchdog、vsock 和 CPU cache tuning。
3. P7-003 使用 ResourceIndex 设备身份实现关机 VM PCI/USB 直通。
4. P7-004 使用配置授权路径根实现 virtiofs/9p 共享目录。
5. P7-005 扩展 NoCloud network-config 支持静态 IPv6 和双栈。
6. P7-006 执行全量回归、Browser QA、Rocky 集成和文档收尾。

## 架构与安全

- 所有远端读取和写入继续经过 RemoteExecutor；页面不提交路径、XML 或设备地址。
- VM 写入统一执行权威刷新、资源锁、结构化 XML Diff、限时确认、写后验证和回滚。
- Host Device 只允许关机 persistent VM；PCI 必须验证 IOMMU group，平台不自动绑定
  vfio-pci、不解绑宿主驱动、不修改启动参数。
- 共享目录必须位于配置授权根，使用 realpath 边界检查；不创建目录、不修改权限，
  不接受符号链接逃逸。virtiofs 不可用时允许显式选择 9p，不自动安装软件。
- IPv6 拒绝 loopback、link-local、multicast、unspecified、跨子网 gateway 和重复 DNS。
- 指标只保存聚合值与 UTC 时间，不保存路径、XML、凭据或原始远端输出；24h 后有界清理。

## 数据与接口

- P7-001 复用 revision 0019 的 `vm_metrics_history`，新增 host metrics 表和 store。
- P7-002 至 P7-004 优先复用现有 VM change plan；若共享字段无法表达设备身份，使用
  独立版本化 payload，不改变页面到内部 Session API 的边界。
- P7-004 新增允许路径配置项，默认空列表并 fail closed。
- P7-005 扩展现有 media creation contract 和 NoCloud 文档，不保存明文密码。

## 错误与恢复

- 采样失败只产生有界缺口，不覆盖上次成功值；节点不可达时页面局部降级。
- XML 写入发生基线变化、能力不足或验证不一致时阻断；已执行但结果不明时 verify-only。
- Host Device 和共享目录恢复只允许原始 XML hash 或目标 XML hash 完整匹配。
- Cloud Image seed 重启恢复继续只读提取文档并比较 SHA-256，不盲目重建。

## 验证

- 每个切片覆盖输入边界、XML 未知内容保留、冲突、幂等、恢复和 Web CSRF。
- P7-003/004/005 在 Rocky 执行 opt-in 真实集成；无法获得真实设备时报告未验证项。
- P7-006 执行 Ruff、mypy、全量 pytest、迁移、容器、Browser QA 与零残留检查。
