# Nexora Project Status

## Current Phase

P9：React 零旧前端与 VM 操作闭环。

## Current Goal

移除所有业务 Jinja 和 React HTML 解析兼容层，补齐节点优先空白磁盘创建、快照、
克隆、关机迁移、删除、重命名、网卡和自动启动完整操作闭环。

## Current Task

2026-08-06 更新：P9 阶段（P9-001~P9-010）全部完成并部署生产。P9-001 至
P9-006 核心清理于 2026-08-05 部署（镜像 `sha256:47f531f429e7`，含空白磁盘、
关机迁移、删除重命名、网卡配置、旧模板清理），随后 P9-007 操作区增强、
P9-008 配置直接保存+XML 历史+待重启、P9-009 创建页三源合并、P9-010 操作闭环
修复（审查 #1-#12）相继完成并部署。迁移链 head 现为 `20260803_0023`
（`vm_xml_history`），生产数据库已升级。

历史决策：2026-08-05 曾实现节点级只读门禁（`Host.read_only`、迁移 0023、
`ensure_host_writable` 守卫与 `HostSummary.read_only` 暴露），经确认 kvm1 仅作为
生产机器需人工保护、无需系统级只读能力后全部回滚，未落地任何代码改动。

P9-002 空白磁盘创建已完成：新建 `vms/blank_creation_*` 模块与 revision 0021 计划表，
同任务先创建空白 qcow2/raw Volume 再定义 VM，含可恢复执行与权威验证；internal
`/vm-create/blank-disk/*` 路由和 `/vms/create/blank-disk` React 页面已接入（现为
创建页"磁盘来源"的"新建空盘"模式）。

P9-003 关机迁移已完成：在克隆基础设施上新增 `preserve_identity` 模式，迁移保留源
UUID 与 MAC、复制全部磁盘与 NVRAM、目标定义并验证，默认保留源定义与磁盘（源端
清理属独立危险操作）；internal `/migrate/*` 路由和 React 关机迁移弹窗已接入。

P9-004 VM 删除与重命名已完成：新建 `vms/remove_*` 模块与 revision 0022 计划表，
删除默认仅 undefine（可逐项选择磁盘/NVRAM），重命名使用 `virsh domrename`，均要求
关机、名称确认、计划确认与权威验证；internal `/remove/*` 路由和 React 删除/重命名
弹窗已接入。

P9-005 网卡完整配置已完成：新建 `xml/network.py` 与 `vms/network_changes.py`，
支持网卡 attach/detach/update（MAC、Bridge/libvirt Network 切换、型号），复用
`VmChangePlan` 三步任务与 live/config 门禁；VM 配置页新增"网络接口"区块。
2026-08-06 修复运行中网卡 detach 断链（从 original XML 提取）与 update 命令
（改 `virsh update-device --live --persistent`），并新增网卡更新弹窗（可改网络/
型号/新 MAC）。

P9-007 操作与总览增强已完成：VM 详情强制关机/强制重启与删除归入独立"危险操作"
行；总览页增加虚拟机状态分布、存储概况与任务排队信息；VM 列表支持按状态与节点
过滤（`/internal/vms` 新增 `state`、`host_id` 参数），过滤与服务端分页协同。

P9-008 VM 配置直接保存 + XML 历史回滚已完成：新增 `vm_xml_history` 表（revision
0023，每 VM 保留最近 10 份配置前 XML 快照）与 save/history/rollback API；
`vm.xml_restore` 任务 handler 已在 `app.py` 注册（三步：validate/define/refresh）；
运行中 VM 配置变更后基于任务时序推断 `needs_restart` 并在列表/节点详情/VM 详情
展示"待重启"标记。

P9-009 创建页三源合并已完成：`/vms/create` 单页内通过"磁盘来源"切换"已有系统盘 /
新建空盘 / 从平台镜像创建"三种方式；创建空盘与平台镜像前必须先选目标存储池；
旧子路径 `/vms/create/blank-disk` 与 `/vms/create/platform-image` 保留并预选模式
（原独立子页面组件已删除）。

P9-010 VM 操作闭环修复（审查 #1-#12）已完成：运行中移除磁盘/网卡断链修复、网卡
更新弹窗、本地 ISO 运行中热插拔（`change-media --live --persistent`）、CPU 拓扑
乘积校验放宽为 ≤（兼容热插拔余量）+ 前端联动约束 + max≤1024/threads∈{1,2}、
内存非法组合预检（discard+anonymous、file+private）、新增"添加光驱"能力、运行中
改 CPU/内存提示、运行中磁盘 attach target 冲突预检。部署镜像
`nexora:rollback-fixops-20260806T113801Z` 保留。

P8-004 至 P8-010 DONE：React 已接管认证、节点接入、两类 VM 创建、存储、媒体、
Bridge/VLAN、VM 生命周期、控制台、任务、审计、设置与交互式网络拓扑。所有 VM
生命周期和控制台操作位于详情页；复杂 VM 配置按确认边界从“配置”进入独立
VM 配置及历史 `/manage/*` 地址。CSRF、计划令牌、资源版本复核及任务队列保持不变。两类创建
均保持 UEFI 与 Secure Boot 独立，默认支持 UEFI 非安全启动，并支持 Driver ISO
与 TPM。主路由使用统一 Design Token、中文浅亮无边框状态 Tag 和语义操作按钮。
2026-08-03 使用生产数据库一致副本完成 16 个主路由、详情页和 `/manage/*` 配置页
的 1280/375px Browser QA；修复 `/networks` 真实关系边空白、链路状态语义、总览
Tag 文字色覆盖，以及节点详情、VM 详情和任务页横向溢出。页面均有内容，无整页或
表格横向溢出、控制台/CSP 错误；网络拓扑 Canvas 正常生成。
正式镜像 `sha256:fb91e77c32b33203120913abb326f2b1e564a48bc90bb6d8976386b9b0379b51`
已部署到 `0.0.0.0:8002`，健康检查与 SQLite `quick_check` 通过；本次回滚镜像
`nexora:pre-storage-wording-20260803T055118Z` 和备份
`/data/backups/nexora-20260803T055119Z.tar.gz` 已保留，早期回滚镜像与备份未删除。
P8-007 已完成节点详情可读化：原始能力键改为“支持/不支持/需关注”，新增厂商、
机型、CPU、内存、NUMA 和实体网卡 MAC 摘要。“刷新节点信息”会先执行 22 步
只读能力探测，再自动刷新资源索引；Rocky 真实节点与 1280/375px QA 通过。
P8-008 将 VM 详情 7 个操作按钮收敛为 36px 紧凑 Flex 按钮组；1280px 保持 8px
间距，375px 自动换为三行，按钮边框无重叠且页面无横向溢出。
P8-009 修复 VM 详情未显示 `host_devices`：详情 API 按同节点规范 PCI 地址关联资源
索引，页面展示直通设备名称、地址、驱动和 IOMMU 组，并将 PCI 网卡计入网络子系统。
kvm3 的 OpenWrt 生产数据副本确认两块 Intel I211 在 1280/375px 均正确显示且无溢出。
P8-010 取消用户可见 Jinja 兼容岛：初始化、登录、VM 配置、历史 `/manage/*`、Host
管理与移除地址均返回 React Shell。配置页覆盖 CPU、内存、磁盘、光驱、PCI/USB、
共享目录和高级设备，并继续复用原预检、Diff、确认、资源版本与任务安全链。
P8-011 在节点“功能支持”增加 PCIe 设备直通判定：IOMMU Group 与 `vfio-pci` 均
就绪时显示支持，仅 IOMMU 就绪时显示需关注，明确无 IOMMU 时显示不支持。kvm3
生产数据副本显示 2 个可直通设备，1280/375px 均无溢出或控制台错误。
P8-012 将顶部导航“节点”入口从拓扑关系语义的 `NodeIndexOutlined` 调整为服务器
语义的 `CloudServerOutlined`，不改变导航布局、颜色和交互；React 测试与构建通过。
P8-013 将“镜像”入口改为 `FileImageOutlined`；设置页移除页面密度和全局等宽字体，
界面固定舒适密度并使用浏览器系统 UI 字体。XML、Diff、命令、UUID、MAC、IP、路径、
哈希和控制台继续使用统一无连字的本机等宽字体栈，后端旧偏好字段仅作兼容保留。
P8-014 修复 React 忽略管理员时区：Session 加载时先配置统一格式化器，节点同步、
任务、审计、登录历史和媒体凭据均按管理员 `timezone` 显示；SQLite 无偏移时间按 UTC
解析。生产账户已核对为 `Asia/Shanghai`，UTC `00:00` → UTC+8 `08:00` 回归通过。
P8-015 将存储创建和确认流程从“预览计划/创建任务”改为“检查创建配置/确认并执行”，
错误提示同步改为配置检查和变更提交语义；预检、XML Diff、确认令牌和任务队列未改变。
P7-006 已完成 Rocky VM/Host 指标、virtiofs 共享目录、IPv6-only 与双栈真实验证。
当前 Rocky 节点没有 IOMMU group，也没有预绑定 `vfio-pci` 设备，因此 PCI 直通
真实执行受硬件条件阻塞；不修改内核、启动配置或随机绑定业务设备。aarch64 与
Rocky 之外 RHEL 系继续按确认边界暂缓。

## Current State

P0 已完成。P1-001 至 P1-003 已在 Rocky 9.7 真实嵌套 KVM 节点通过 root 私钥、
普通用户密码 SSH/免密 sudo、加密私钥口令、传统/模块化 libvirt、接入、发现、
镜像复制和零残留验证。Debian 13 nested KVM 已通过普通用户 sudo、能力探测、接口
与已有 VM 自动发现。Ubuntu 24.04 LTS nested KVM 已通过普通用户 sudo、能力探测、
接口与已有 VM 自动发现及零残留销毁；Rocky 之外 RHEL 系矩阵暂缓。P3-001 媒体扫描、受保护 Range 与
镜像复制、P3-002 Pool 与 P3-003 Volume 管理已完成。P2-001 已完成生命周期、
CPU、内存、持久化 Disk、本地及平台 ISO CD-ROM 切片。平台 ISO 已在 Rocky 通过
Range、撤销、缓存复制、QEMU 启动与零残留验证。已有 Snapshot 已完成只读展示；
安全关机 qcow2 的 Snapshot 创建、leaf 删除和数据恢复已通过真实 Rocky 验证。
VM `domstats` 实时采样已通过真实 Rocky 验证。从同节点未引用 managed qcow2/raw
Volume 创建 BIOS persistent VM 已完成；可选择现有 Bridge/libvirt Network，并通过
真实 libvirt Network、readonly SATA ISO、自动 MAC、启动和零残留清理验证。
平台 qcow2/raw 复制后创建使用 revision 0015 可恢复任务，已通过真实 Rocky 的
SSH 复制、SHA-256、Volume 自动发现、定义、启动和精确清理。
Cloud Image 已支持 hostname、普通用户、SSH 公钥、SHA-512 crypt 密码、DHCP/
静态 IPv4 NoCloud seed 及复制后 grow-only 扩容；真实节点验证 8→16 MiB 扩容、
seed 内容恢复、readonly 挂载、启动及双 Volume/partial 零残留。
P6-002 已将品牌蓝、青色和暖色强调 Token 落地到全站组件，统一卡片、导航、按钮、
表单、表格、Badge 与认证页层次；375/768/1024/1440px 无横向溢出且触控目标
不小于 44px。最终镜像双断点复核无页面或控制台错误。
Guest Agent 已支持 channel 配置识别、运行态 ping、Hostname 与全局 IP；固定
virsh 命令只读采集，远端不可用时局部降级。真实 Rocky 已验证 stopped/unavailable，
本机 HTMX 15 秒卡片已通过 375px Browser QA。
串口控制台使用 revision 0016 一次性摘要 Token，绑定管理员 Session、host、VM、
用途与 Origin，经 AsyncSSH PTY 桥接固定 `virsh console --safe`。真实 Rocky 握手、
xterm Browser QA、浏览器关闭及远端零进程残留均已验证。
VNC 使用同一会话模型，经 AsyncSSH 回环 Tunnel、Nexora 单次 websockify worker
和 noVNC 1.7.0 提供 RFB；真实 Rocky banner 与浏览器 canvas 均已验证，关闭后
worker/Tunnel/Session 零残留。PyPI websockify 因传递 Redis 依赖被拒绝并移除。
关机完整克隆使用 revision 0017 限时计划与 `vm.clone` 可恢复任务，生成新 UUID/MAC，
经双 SSH 1 MiB chunk relay 复制全部 qcow2/raw 文件盘和 NVRAM，执行 size/SHA-256
校验与 hard-link 无覆盖发布。真实 Rocky 已完成复制、启动目标、源保持和零 partial；
跨节点路径已实现架构及 Bridge/libvirt Network 复核，待第二节点实测。

## Completed Work

- 创建精简项目级 `AGENTS.md`。
- 固化产品定位、技术栈、范围、阶段和非目标。
- 固化单容器运行、远端管理、任务、资源、XML、媒体、存储和网络设计。
- 固化多节点复合资源身份与内部 API 节点作用域。
- 固化凭据、Web、SSH、XML、路径、媒体和审计安全基线。
- 输出 P0 详细路线图、验收目标和首批测试范围。
- 建立 FastAPI application factory、Settings、健康检查和 Python 测试。
- 建立 SQLite/Alembic 基础并验证 WAL、FK、超时和迁移。
- 构建并运行非 root 单容器，验证无 KVM/libvirt socket/设备映射。
- 完成管理员初始化、登录、退出、改密、偏好和登录历史。
- 完成 Argon2、Session、CSRF、限速、可信 Host 与浏览器 QA。
- 完成 AES-256-GCM、AAD、key version、轮换与 fail-closed 测试。
- 完成 Host Key 确认/变化阻断和真实临时 sshd 验证。
- 完成 typed RemoteExecutor、严格 SSH argv、取消、限额和审计事件。
- 完成 Task/TaskStep、原子 claim、lease、心跳、检查点和取消。
- 完成单进程重启中断识别、有限停机和基础任务中心页面。
- 完成本地 Tabler/Icons 构建、统一导航、响应式页面和空状态。
- 验证运行镜像不含 Node.js，浏览器桌面/移动端无错误和横向溢出。
- 完成 lxml 安全入口、版本化 C14N2 hash、Diff 和 CPU topology 局部修改。
- 验证 XXE/DOCTYPE/XInclude、资源上限与未知 XML 内容保留。
- 完成 `nexora-ops` 初始化、SQLite 一致备份、校验恢复与 recovery point。
- 完成部署、媒体挂载、升级、回滚和故障排查模块化文档。
- 最终 P0 镜像验证 healthy、非 root、非 privileged、无设备和运行时 Node.js。
- 完成 Host、凭据、Host Key、能力与远端命令审计模型和 0004 迁移。
- 完成两阶段 Host Key 确认、加密凭据保存和严格 known_hosts 建立。
- 完成 AsyncSSH 密码/内存私钥执行后端、输出限额、超时和取消。
- 完成 19 步只读节点能力探测、TaskStep 检查点和能力持久化。
- 完成节点列表、添加、指纹确认、能力详情页面与桌面/移动端 QA。
- 完成 ResourceScan、ResourceIndex、ResourceDocument 和 0005 迁移。
- 完成按类型 generation、失败扫描不误报 missing 和本地标签/备注保留。
- 完成 VM/快照、Pool/Volume、libvirt Network、接口和 PCI/USB 发现。
- 完成 persistent/live hash、带外变化保持、资源摘要和手动重新扫描。
- 按当前 virsh 官方参数修正 inactive Pool 与 Volume 枚举兼容路径。
- 完成 ResourceWriteGuard，允许 hash 未变的刷新并阻断危险资源状态。
- 完成 10 分钟节点移除计划、摘要 token、名称确认和执行前集合重验。
- 完成仅 Nexora 临时路径/unit 清理、本地级联删除和脱敏 tombstone。
- 完成移除页面、三步持久化任务、失败状态恢复和零业务删除测试。
- 完成节点作用域 VM 列表、详情、Persistent XML 和生命周期表单。
- 完成 10 类生命周期动作的状态矩阵、UUID 命令和最终状态轮询。
- 完成 Domain 数据库租约锁、并发阻断、权威刷新和带外变更守卫。
- 完成生命周期三步持久化任务、取消处理和强制操作名称确认。
- 完成桌面/375px VM 页面 QA 与 revision 0007 单容器运行验证。
- 完成 CPU topology 结构化表单、默认值读取和乘积校验。
- 完成远端 `virt-xml-validate`、局部 XML 变换与可审查 Diff。
- 完成 10 分钟确认计划、原始/目标 XML 和双端 hash 持久化。
- 完成 CPU 异步应用、资源锁、写后验证和失败恢复原始 XML。
- 完成 CPU 页面桌面/375px QA 与 revision 0008 单容器运行验证。
- 完成 current/max memory 与 memoryBacking 安全局部 XML 变换。
- 完成 HugePages page、未知属性/元素保留和受限枚举校验。
- 完成内存确认计划、类型绑定、异步应用和失败回滚。
- 完成 CPU/内存/生命周期同 VM 入队互斥与数据库锁兜底。
- 完成内存页面桌面/375px QA 与 `nexora:p2-memory` 单容器验证。
- 完成 MediaScan/MediaItem generation 索引与 revision 0009 迁移。
- 完成 ISO/qcow2/raw 限界枚举、`O_NOFOLLOW` 哈希和文件身份复核。
- 完成 qemu-img 格式/虚拟容量/backing chain 解析与外部路径脱敏。
- 完成失败扫描原子保持、missing 状态、本地备注保留和 3 步持久化任务。
- 完成媒体库页面、桌面/375px QA 与只读 `/library` 单容器验证。
- 完成 digest-only MediaCredential、SHA 版本绑定、最长 30 天租约和撤销。
- 完成 URL 无秘密的 Bearer 认证与一次性凭据展示页面。
- 完成 HEAD/GET/单 Range、suffix、206/416、ETag 和 If-Range。
- 完成流式 `O_NOFOLLOW` 读取与 device/inode/size/mtime 版本复核。
- 完成凭据页桌面/375px QA 与 revision 0010 单容器验证。
- 完成权威 Pool 刷新、资源租约锁与长任务锁心跳续租。
- 完成 AsyncSSH 流式镜像复制、任务专属 `.partial`、大小和 SHA-256 校验。
- 完成 hard-link 无覆盖发布、最终文件幂等识别和中断后显式安全重试。
- 完成任务恢复 CSRF 页面、桌面/375px QA 与真实临时 SSH 传输测试。
- 完成 Rocky 9.7 嵌套 KVM 环境、已有 VM/Pool 纳管、复制与移除零残留验证。
- 完成 `nexora:p3-image-copy` revision 0010 单容器最终运行验证。
- 完成 dir/netfs Pool 结构化输入、路径和 NFS mount option 白名单。
- 完成 revision 0011 持久化 Pool 预览、Diff、限时确认与恢复状态。
- 完成 define/build/start/stop/refresh/autostart、资源锁和权威写后验证。
- 完成 undefine 前 VM 引用扫描、带外变化阻断与业务文件保留。
- 修正 `virt-xml-validate -` 标准输入兼容性和 Pool 易变容量 hash。
- 完成 Rocky 回环 NFSv3 的 dir/netfs 全生命周期真实集成测试。
- 完成存储页面 1280/375px QA 与 44px 操作触点。
- 完成 `nexora:p3-storage` revision 0011 单容器最终运行验证。
- 完成 revision 0012 Volume 创建、只扩容、显式删除及持久化确认任务。
- 完成 Pool UUID + Volume Key 身份、Pool/Volume 双锁和 VM 引用阻断。
- Volume 配置 hash 排除 allocation、physical、timestamps 等易变运行统计。
- 完成 dir 与回环 NFS netfs qcow2 创建、扩容、删除真实集成及零残留复核。
- 完成已有 Disk 全量展示及同节点 managed qcow2/raw Volume 选择。
- 完成 persistent XML Disk 挂载/卸载、限时 Diff 确认和三步持久化任务。
- 完成 VM/Volume 基线重验、双资源锁、引用阻断和卸载默认保留 backing。
- 写后允许 libvirt 为新 Disk 生成 PCI address，同时复核其余 Domain XML 未变化。
- 完成运行中 VM config-only 挂载/卸载真实验证及测试资源零残留复核。
- 完成已有 persistent CD-ROM 展示、本地 ISO 换盘与弹出。
- 本地 ISO 仅接受同节点 managed dir/netfs raw `.iso` Volume。
- 完成 VM/ISO 双基线复核、双资源锁、设备身份校验和 backing 保留。
- 完成运行中 VM CD-ROM config-only 真实验证与原始 XML 恢复。
- 完成平台 ISO 源 IP/VM/媒体 SHA-256 绑定的 HTTP Range 直连设计。
- 完成 QEMU URL 无 Bearer、cookie、query secret 的 Domain XML 与撤销流程。
- 完成受控 `/var/tmp` ISO 缓存、任务 partial、大小/SHA 校验和无覆盖发布。
- 完成全节点 Domain 引用重验、共享缓存保留与零引用精确删除。
- 完成 Rocky HTTP driver whitelist 识别及缓存 QEMU 启动真实验证。
- 完成 domcapabilities system QEMU machine-none/QMP HTTP 预探测；拒绝时撤销凭据。
- 固化现代明亮、鲜活彩色强调的后续 Design Token 与 P6-002 任务。
- 完成 VM 详情页 Snapshot 名称、时间、状态、内存/磁盘模式和原始 XML 展示。
- 完成 host/domain 作用域、2,000 条上限、XML 转义和不触发远端扫描。
- 完成 Rocky 平台外 internal Snapshot 自动发现、无需导入及零残留复核。
- 完成 revision 0013 独立 Snapshot 持久化预览、确认与结果状态。
- 完成关机持久化 VM 的原子 internal Snapshot 创建、VM/Snapshot 双锁和写后验证。
- 完成真实 Rocky 持久化任务创建快照、权威 XML 验证及 VM/磁盘零残留复核。
- 完成 Snapshot parent/current 发现、internal leaf 删除和相邻链/VM XML 验证。
- 完成配置等价 current internal leaf 恢复、VM 名称确认及危险 flag 禁用。
- 完成 Rocky `qemu-io` 模式 A/B/A 字节级磁盘回退和零残留验证。
- 完成 VM domstats 严格解析、聚合速率和 2,000 项/15 分钟有界差分缓存。
- 完成认证 HTMX 5 秒性能卡片及远端失败局部降级。
- 完成 Rocky 运行中 VM 连续采样、内存与非负速率真实验证。
- 完成 revision 0014 VM 创建计划、managed Volume 权威预检和三步持久化任务。
- 完成结构化 BIOS Domain XML、远端 schema 校验、Diff 与 Volume→VM 双锁。
- 完成 Rocky qcow2 导入定义、实际启动、精确清理和本机创建页 Browser QA。
- 完成本机 `/data` 备份、0013→0014 自动迁移和当前源码单容器重部署。
- 完成 host-scoped 物理口、VLAN、Bridge、vnet/tap、VM NIC 只读拓扑与关系表。
- 使用 `ip -d -j link show` 保留接口类型，并在真实 Rocky 验证 Bridge/vnet/管理链。
- 完成有界分页、节点/结果筛选、脱敏摘要和 HTML 转义的审计中心。
- 完成现代明亮鲜活全站 Token、统一组件、四断点与最终部署 Browser QA。
- 完成真实普通用户密码 SSH、免密 sudo、严格 Host Key、审计脱敏与零残留测试。
- 完成真实加密 Ed25519 私钥口令、内存凭据、审计脱敏与零残留测试。
- 完成真实 modular libvirt 五 daemon 接入、资源发现、复制、移除与原状态恢复。
- 完成 Debian 13 nested KVM 普通用户接入、能力、接口、已有 VM 发现与零残留。
- 完成 Ubuntu 24.04 LTS nested KVM 普通用户接入、能力、接口、已有 VM 发现与零残留。
- 完成 VM 详情页 NUMA、CPU Pinning、Watchdog 和 vsock 只读展示。
- 完成磁盘挂载高级参数（cache/io/discard/serial/readonly/shareable）页面与 XML 变更。
- 完成创建向导扩展：系统盘 Bus 选择（virtio/sata/scsi）与 CPU 模式（host-model/host-passthrough）。
- 完成磁盘热插拔：运行中 VM 实时挂载/卸载磁盘（virsh attach-device/detach-device --live --persistent）。
- 完成 P4-002 Bridge/VLAN 安全写入和 P5-001 NUMA/CPUTune 写入设计文档。
- 完成 Windows/UEFI/TPM VM 创建：guest_profile/firmware/secure_boot/tpm2/第二 ISO、能力驱动 XML 生成。
- 完成 P8-001：独立 React 19、TypeScript、Vite 与 Ant Design 6 工程、内部 Session
  API、CSP nonce、认证 `/ui-preview` Shell、manifest fail-closed 和多阶段镜像构建。
- 完成 P8-001 四断点 Browser QA 与正式部署；运行镜像不含 Node/npm，旧 Jinja URL
  未接管，旧镜像与一致备份均已保留。
- 完成 P8-002：React 接管 `/`、`/hosts`、`/vms`，新增分页内部 API、桌面表格、
  移动卡片、中文状态、Session 偏好同步和 44px 触控目标。
- 完成 P8-002 四断点 Browser QA、379 tests 全量回归与正式可回滚部署。
- 完成 P8-003：React 节点/VM 详情、24h 指标、Guest Agent、设备、快照和安全
  格式化 XML；旧写操作由同源 `/manage/*` 继续承载。
- 建立 `static/css/design-tokens.css` 和 Ant Design Theme 双层 Token，统一按钮、
  Tag、表格、卡片、表单、菜单、弹窗、分页、Hover/Focus/Disabled 与技术视图。
- 完成 375/768/1280/1440px Browser QA；无页面横向溢出、渐变、状态圆点、
  可见彩色 Tag 边框、卡片阴影或浏览器错误。
- 完成 P8-004 第一批：React managed Volume VM 创建配置、受限资源内部 API、
  原地 Domain XML Diff、确认任务和 UEFI 非安全启动。
- 完成 P8-004 第二批：React Host Key 扫描/显式确认和平台镜像 VM 创建；保留凭据
  不回显、变化阻断、复制校验、Cloud-init、扩容恢复及 Driver ISO 权威复核。
- 完成 P8-004 收尾：React 存储池/卷、媒体凭据/复制、Bridge/VLAN 安全预检与应用，
  以及 VM 详情生命周期和危险操作名称确认。
- 完成 P8-005：React 任务取消/恢复、审计筛选、账户设置、节点扫描/移除、串口、
  VNC 与 Cytoscape 拓扑；控制台依赖按需加载并在关闭时释放连接。
- 完成 P8-006：主页面全部由 React 优先接管，固定语义 Token 消除重复 Hover 色与
  组件硬编码拓扑色；认证和复杂 VM 配置保留为隔离兼容岛。
- 完成 Rocky VM/Host 指标、IPv6-only/双栈和 virtiofs 真实验证；virtiofs 写后
  仅容许 libvirt 规范排序与目标设备自动 PCI address，并恢复原 XML/目录。
- 部署 P7 收尾镜像 `sha256:8c977dc0...`；备份
  `/data/backups/nexora-20260801T083635Z.tar.gz`，回滚标签
  `nexora:pre-p7-closeout-20260801T163634`，正式服务 healthy。
- 完成 Cytoscape 交互式网络拓扑图：节点着色、管理链路高亮、关系边标签、无 JS 回退表格。
- 完成 P5-001 NUMA/CPUTune 写入：xml/numa.py + xml/cputune.py 变换与测试。
- 完成 P5-002 跨节点克隆：修复 qemu-img -U 锁、XML 跨节点兼容（移除 emulator/machine）、Rocky->Ubuntu 实测 PASS。
- 完成节点添加表单错误后数据保留。

## In Progress

- P7-006 BLOCKED：仅等待具备 IOMMU group 和预绑定 `vfio-pci` 测试设备的 Rocky
  节点执行 PCI 直通真实验证。

## Remaining Work

- 补充自动化测试缺口：`configuration/history|rollback` Web 单测、`needs_restart=True`
  场景单测、`is_attachable_volume` 直接单元测试（见 TEST_STATUS 与审计报告）。
- 在具备隔离测试设备的 Rocky 节点验证预绑定 `vfio-pci` PCI 直通和零残留清理。
- 真实 Rocky 远端跑 `tests/integration/test_remote_vm_clone.py`（跨节点迁移）。
- 启用 agent-browser 复核 1280/375px 密度（NEW-2 密度收紧未做视觉 QA）。
- aarch64 与 Rocky 之外 RHEL 系发行版验证暂缓，不计入 P7 验收。

## Known Problems

- `shellcheck` 未安装，入口脚本只完成实际容器运行验证。
- 长期节点：Rocky 9.7（root，RHEL 兼容系，libvirt 11.10/QEMU 10.1，全功能）；
  Ubuntu 26.04 LTS（ubuntu 用户，免密 sudo，libvirt 12.0/QEMU 10.2，全功能，
  可任意操作）；
  Debian 13 与 Ubuntu 24.04 LTS 使用临时 nested KVM 完成后已零残留销毁。
- NFS 仅在该节点以回环 Export 作为隔离测试夹具，尚未覆盖独立 NFS Server。
- Rocky QEMU 10.1.0 即使安装 curl block driver 仍拒绝 HTTP whitelist，使用已验证
  的缓存回退；后续发行版需分别探测直连能力。

## Blockers

无当前执行阻塞。历史分支恢复因配置与磁盘链风险明确保持只读。

## Pending Confirmations

- Windows/UEFI/Secure Boot/TPM 共享 VM 创建契约已确认；设计见
  `2026-07-29-windows-uefi-tpm-create-design.md`。
- Cytoscape 图形拓扑 npm 依赖已确认；将新增 cytoscape 依赖并更新 lockfile。

## Files Changed

- 根目录：`AGENTS.md`、`ARCHITECTURE.md`、`PROJECT_STATUS.md`、`ROADMAP.md`
- 根目录：`DECISIONS.md`、`CHANGELOG.md`、`TEST_STATUS.md`、`SECURITY.md`
- 产品：`docs/product/REQUIREMENTS.md`、`docs/product/SCOPE.md`
- 架构：`REMOTE_MANAGEMENT.md`、`TASK_SYSTEM.md`、`RESOURCE_SYNC_XML.md`
- 架构：`MEDIA_STORAGE.md`、`NETWORKING.md`、`RUNTIME_DEPLOYMENT.md`
- 架构：`CONSOLE_MIGRATION.md`、`FRONTEND.md`（均位于 `docs/architecture/`）
- 测试：`docs/testing/ACCEPTANCE.md`
- 索引：`docs/README.md`
- 开发：`docs/development/README.md`
- 开发：`docs/development/2026-07-28-documentation-baseline-design.md`
- 应用：`pyproject.toml`、`uv.lock`、`src/nexora/`、`tests/`
- 前端：`static/css/nexora.css`、`templates/`、`design-system/nexora/MASTER.md`
- 网络：`src/nexora/networking/`、`tests/networking/`、网络拓扑集成测试
- 审计：`src/nexora/audit/read_service.py`、`tests/audit/`、审计 Web 测试
- 数据库：`alembic.ini`、`alembic/`
- 容器：`Dockerfile`、`docker-compose.yml`、`.env.example`、`scripts/`
- 设计：`design-system/nexora/MASTER.md`
- P1：`src/nexora/hosts/`、`src/nexora/audit/`、`templates/hosts/`
- P1：`tests/hosts/`、`tests/remote/`、`tests/audit/`、`tests/web/test_hosts.py`
- P1：`src/nexora/resources/`、`tests/resources/`、Alembic revision 0005
- P1：`hosts/removal*`、`web/routes/host_removal.py`、Alembic revision 0006
- P2：`src/nexora/vms/`、`templates/vms/`、`tests/vms/`、`tests/web/test_vms.py`
- P2：`src/nexora/tasks/locks.py`、Alembic revision 0007
- P2：`vms/cpu_changes.py`、`vms/change_models.py`、Alembic revision 0008
- P2：`web/routes/vm_cpu.py`、`templates/vms/cpu_preview.html`
- P2：`xml/memory.py`、`vms/memory_changes.py`、`web/routes/vm_memory.py`
- P2：`templates/vms/memory_preview.html`、`tests/xml/test_memory.py`
- P2：`xml/disk.py`、`vms/disk_changes.py`、`web/routes/vm_disk.py`
- P2：`templates/vms/disk*.html`、`tests/vms/test_disk_changes.py`
- P2：`xml/cdrom.py`、`vms/cdrom_changes.py`、`web/routes/vm_cdrom.py`
- P2：`templates/vms/cdrom*.html`、`tests/vms/test_cdrom_changes.py`
- P2：`vms/clone_*.py`、`web/routes/vm_clone.py`、`templates/vms/clone*.html`
- P2：Alembic revision 0017、`tests/vms/test_clone_*`、`test_remote_vm_clone.py`
- P2/P3：`media/iso_cache.py`、`vms/cached_iso_changes.py`
- P2/P3：`web/routes/vm_platform_iso.py`、`web/routes/vm_cached_iso.py`
- P2/P3：`tests/integration/test_remote_platform_iso.py`
- P2：`vms/read_service.py`、`templates/vms/snapshot_card.html`
- P2：`vms/snapshot_*.py`、`web/routes/vm_snapshot.py`、revision 0013
- P2：`templates/vms/snapshot_preview.html`、`tests/vms/test_snapshot_service.py`
- P2：`templates/vms/snapshot_delete_preview.html`
- P2：`vms/snapshot_revert_service.py`、`web/routes/vm_snapshot_revert.py`
- P2：`templates/vms/snapshot_revert_preview.html`
- P2：`vms/metrics.py`、`web/routes/vm_metrics.py`、`templates/vms/metrics_card.html`
- P2：`tests/vms/test_metrics.py`、`tests/web/test_vm_metrics.py`
- P2：`tests/integration/test_remote_snapshot_discovery.py`
- 开发：`docs/development/2026-07-29-vm-snapshot-read-design.md`
- 开发：`docs/development/2026-07-29-vm-snapshot-write-design.md`
- 开发：`docs/development/2026-07-29-vm-snapshot-delete-design.md`
- 开发：`docs/development/2026-07-29-vm-snapshot-revert-design.md`
- 开发：`docs/development/2026-07-29-vm-realtime-metrics-design.md`
- P3：`src/nexora/media/`、`templates/media/`、`web/routes/media.py`
- P3：`tests/media/`、`tests/web/test_media.py`、Alembic revision 0009
- P3：`media/credentials.py`、`media/ranges.py`、`web/routes/media_content.py`
- P3：`templates/media/credential.html`、Alembic revision 0010
- P3 草案：`media/copy*.py`、`remote/transfer.py`、`templates/media/copy.html`
- P3 草案：`web/routes/media.py`、`app.py`、`tests/media/test_copy.py`
- P3：`src/nexora/storage/`、`templates/storage/`、`web/routes/storage*.py`
- P3：`tests/storage/`、`tests/web/test_storage.py`、Alembic revision 0011
- P3：`storage/volume*.py`、`resources/storage_parser.py`、revision 0012
- P3：`templates/storage/volume*.html`、`web/routes/storage_volume.py`
- 集成：`tests/integration/test_remote_kvm.py`、`test_remote_storage.py`
- 集成：`tests/integration/test_remote_vm_disk.py`
- 集成：`tests/integration/test_remote_vm_cdrom.py`
- 测试文档：`docs/testing/INTEGRATION_ENVIRONMENT.md`
- VM 创建：`src/nexora/vms/creation_*.py`、`templates/vms/create*.html`
- VM 创建测试：`tests/vms/test_creation*.py`、`tests/web/test_vm_create.py`
- VM 创建集成：`tests/integration/test_remote_vm_create.py`
- 平台镜像创建：`vms/media_creation_*.py`、`web/routes/vm_create_media.py`
- 平台镜像页面：`templates/vms/create_media*.html`、Alembic revision 0015
- 平台镜像测试：`tests/vms/test_media_creation.py`、
  `tests/integration/test_remote_vm_media_create.py`
- Cloud Image：`vms/cloud_init.py`、`vms/cloud_init_remote.py`
- Cloud Image 测试：`tests/vms/test_cloud_init.py`
- Guest Agent：`vms/guest_agent.py`、`web/routes/vm_guest_agent.py`
- Guest Agent 页面/测试：`templates/vms/guest_agent_card.html`、
  `tests/vms/test_guest_agent.py`、`tests/web/test_vm_guest_agent.py`
- HTMX 运行资源：`package.json`、`scripts/build-assets.mjs`、`templates/base.html`
- 控制台：`src/nexora/consoles/`、`web/routes/vm_console.py`、revision 0016
- 串口页面：`templates/vms/serial_console.html`、`static/js/serial-console.js`
- 串口测试：`tests/consoles/`、`tests/web/test_vm_console.py`、
  `tests/integration/test_remote_vm_serial_console.py`
- VNC：`consoles/vnc.py`、`consoles/websockify_worker.py`、
  `templates/vms/vnc_console.html`、`static/js/vnc-console.js`
- VNC 测试：`tests/consoles/test_vnc.py`、
  `tests/integration/test_remote_vm_vnc_console.py`

## Tests Run

- 综合文件、行数、章节和尾随空白检查：PASS，22 个文档，最大 90 行。
- 根目录必需文件 shell 检查：PASS，8 个文件齐全。
- 关键决策 `rg` 一致性检查：PASS。
- `PROJECT_STATUS.md` 16 个必填章节检查：PASS。
- `uv run pytest -q`：PASS，166 tests。
- `nexora-ops` init/backup/restore/check 演练：PASS。
- `docker build --tag nexora:p0-complete .`：PASS。
- Ruff check/format 与 mypy strict：PASS。
- Docker build/run：PASS；健康、UID 10001、非 privileged、无设备映射。
- agent-browser：PASS；桌面/移动认证流程无页面与控制台错误。
- P1 节点页 agent-browser：PASS；1440px/375px 无溢出或控制台错误。
- `docker build --tag nexora:p1-review .`：PASS。
- P1 运行镜像：PASS；revision 0004、5 个 Host 相关表、无 Node.js。
- P1 资源页 agent-browser：PASS；1280px/375px 无溢出或控制台错误。
- `nexora:p1-resources`：PASS；revision 0005、3 个资源索引表、当前源码构建。
- 节点移除 agent-browser：PASS；桌面/375px 无溢出或控制台错误。
- `nexora:p1-complete`：PASS；revision 0006、非 root、非 privileged、0 devices。
- VM 页面 agent-browser：PASS；1280px/375px 无溢出或控制台错误。
- `nexora:p2-lifecycle`：PASS；healthy、revision 0007、UID 10001、0 devices。
- CPU 页面 agent-browser：PASS；1280px/375px 无溢出或控制台错误。
- `nexora:p2-cpu`：PASS；healthy、revision 0008、非 root、无 Node.js。
- 内存页面 agent-browser：PASS；1280px/375px 无溢出或控制台错误。
- `nexora:p2-memory`：PASS；healthy、revision 0008、非 root、0 devices。
- 媒体库 agent-browser：PASS；真实扫描任务，1280px/375px 无溢出或错误。
- `nexora:p3-media-index`：PASS；revision 0009、`/library:ro`、qemu-img 可用。
- ISO 凭据页 agent-browser：PASS；一次性展示，1280px/375px 无溢出或错误。
- `nexora:p3-media-range`：PASS；revision 0010、library ro、非 root。
- 镜像复制/恢复定向验证：PASS；35 tests。
- `uv run pytest -q`：PASS；177 passed，1 integration skipped。
- 真实 Rocky/KVM 集成：PASS；1 test，14.22s。
- 节点移除外部复核：PASS；VM/Pool/复制文件存在，5 类临时实体为 0。
- 任务恢复 agent-browser：PASS；1280/375px、44px 按钮、无溢出或错误。
- `nexora:p3-image-copy`：PASS；healthy、revision 0010、UID 10001、0 devices。
- Ruff format/check、mypy 124 source files、npm audit、Compose：PASS。
- `git diff --check`：PASS。
- 最终 `uv run pytest -q`：PASS；295 passed，21 skipped。
- Ruff format/check：PASS；mypy：224 个 source files PASS。
- `npm run build:assets` 与 `npm audit`：PASS；0 vulnerabilities。
- 最终 Rocky 网络拓扑：PASS；10.29s，Bridge/vnet/管理链和默认路由均存在。
- 最终 Browser QA：PASS；375/1440px 无溢出、控件不小于 44px、零页面/控制台错误。
- 真实密码 SSH/普通用户 sudo：PASS；1 test，0.91s，远端夹具残留为 0。
- 真实加密私钥口令：PASS；1 test，2.50s，用户/Home/进程/临时目录残留为 0。
- 真实模块化 libvirt：PASS；1 test，13.61s，恢复传统服务且业务资源/复制文件保留。
- Debian 13 nested KVM：PASS；1 test，14.34s，已有 VM 自动发现且完整销毁。
- Ubuntu 24.04 LTS nested KVM：PASS；1 test，已有 VM 自动发现及零残留销毁。
- 新增集成测试后 Ruff、mypy 224 source、npm audit、Compose 与 diff check：PASS。
- `nexora:latest`：PASS；镜像 `dc7c02b1...`、revision 0018、UID 10001、
  非 privileged、0 devices、SQLite quick_check ok。
- 高级 XML 配置只读解析定向回归：PASS；10 tests。
- 磁盘高级参数 XML/验证定向回归：PASS；7 tests。
- 创建向导 disk_bus/cpu_mode 定向回归：PASS；6 tests。
- 磁盘热插拔 live 执行路径：PASS；stub 测试通过。
- `uv run pytest -q`：PASS；318 passed，21 skipped。
- 存储契约、XML、任务、生命周期、带外冲突与引用守卫：PASS；25 tests。
- `uv run pytest -q`：PASS；214 passed，3 opt-in skipped。
- 真实 Rocky/KVM+NFS 集成：PASS；2 tests，49.64s。
- 真实 Pool 复核：PASS；dir/netfs 定义和挂载清理，NFS 业务文件保留。
- 存储页 agent-browser：PASS；1280/375px、无页面溢出或错误、44px 操作项。
- `docker build -t nexora:p3-storage .`：PASS；digest `212dfcec...`。
- `nexora:p3-storage`：PASS；healthy、revision 0011、UID 10001、0 devices。
- Ruff、mypy 140 source files、npm audit、Compose 与 diff check：PASS。
- Volume 输入/XML/迁移/无覆盖创建定向回归：PASS；22 tests。
- 真实 Rocky qcow2 Volume 创建：PASS；1 test，22.48s；测试资源已清理。
- Ruff、mypy 148 source files、全量 214 tests 与 diff check：PASS。
- Volume 创建/扩容/删除与引用保护定向回归：PASS；48 tests。
- `uv run pytest -q`：PASS；221 passed，4 opt-in skipped。
- 真实 Rocky dir/netfs qcow2 Volume：PASS；2 tests，66.20s。
- 真实 Volume 复核：PASS；两个 Pool、Target 和 NFS Volume 均无残留。
- `nexora:p3-volume`：PASS；healthy、revision 0012、Volume plan 表存在。
- 存储卷页面 agent-browser：PASS；创建/扩容/删除入口可访问且标签完整。
- VM Disk 定向回归：PASS；13 tests，含 libvirt address 规范化与回滚。
- 真实 Rocky 运行中 VM Disk：PASS；1 test，31.65s；挂载、卸载、卷保留。
- 真实 Disk 零残留复核：PASS；测试 Pool、Volume、Target 和 VM 引用均不存在。
- `uv run pytest -q`：PASS；229 passed，5 opt-in skipped。
- Ruff format/check、mypy 154 source files、npm audit/build、Compose、diff：PASS。
- VM Disk Browser QA：PASS；1280/375px 无页面溢出或控制台错误，按钮 44px。
- `nexora:p2-vm-disk`：PASS；healthy、revision 0012、UID 10001、0 devices。
- CD-ROM XML/计划/页面定向回归：PASS；9 tests。
- 真实 Rocky 运行中 VM CD-ROM：PASS；1 test，34.29s；弹出并重新挂载。
- 真实 CD-ROM 零残留复核：PASS；原 VM XML 恢复，测试资源全部不存在。
- `uv run pytest -q`：PASS；233 passed，6 opt-in skipped。
- Ruff、mypy 157 source files、npm audit/build、Compose 与 diff：PASS。
- CD-ROM Browser QA：PASS；1280/375px 无溢出/控制台错误，按钮 44px。
- `nexora:p2-cdrom`：PASS；healthy、revision 0012、UID 10001、0 devices。
- 平台 ISO 缓存定向回归：PASS；6 tests。
- 真实 Rocky Range/撤销/预探测/缓存/QEMU：PASS；1 test，24.90s。
- 真实零残留复核：PASS；专用 VM、缓存文件、测试服务监听均为 0。
- `uv run pytest -q`：PASS；241 passed，7 opt-in skipped。
- Ruff、mypy：PASS；162 source files。
- npm assets/audit、Compose 与 diff：PASS；0 vulnerabilities。
- `nexora:p2-platform-iso`：PASS；healthy、revision 0012、UID10001、0 devices。
- 平台 ISO Browser QA：PASS；1280/375px、44px、无溢出或控制台错误。
- 验证纠正：npm script 应为 `build:assets`；Compose 需占位必填密钥；隔离容器
  bind mount 需为 UID10001 可写。纠正后均通过，临时容器与目录已清理。
- 初版 `qemu-img` 探测产生假阳性；真实测试捕获后改为 system QEMU blockdev
  探测并复测通过，专用 VM、缓存与监听再次确认为 0。
- Snapshot 定向回归：PASS；13 tests。
- 真实 Rocky 带外 Snapshot 发现：PASS；1 test，12.21s，VM/磁盘无残留。
- Snapshot Browser QA：PASS；1280/375px、XML 控件 44px、无错误。
- Snapshot 创建与 migration 定向回归：PASS；7 tests。
- 真实 Rocky Snapshot 发现与任务创建：PASS；2 tests，29.04s，VM/磁盘无残留。
- `uv run pytest -q`：PASS；243 passed，9 opt-in skipped。
- `uv run ruff check .`、`uv run mypy src/nexora`、`git diff --check`：PASS。
- 本机 `nexora:latest`：PASS；healthy、revision 0013、管理员保留、UID10001、
  非 privileged、0 devices、无运行时 Node.js。
- 迁移前备份：`/data/backups/nexora-20260729T024428Z.tar.gz`。
- 部署后登录页 Browser QA：PASS；1280/375px 无横向溢出、页面或控制台错误。
- Browser CLI 首次误用 `viewport` 子命令；改为 `set viewport` 后移动端复测通过。
- Snapshot leaf 删除定向回归：PASS；16 tests。
- 真实 Rocky Snapshot 创建与 leaf 删除：PASS；2 tests，33.53s，VM/磁盘无残留。
- `uv run pytest -q`：PASS；244 passed，9 opt-in skipped。
- leaf 删除部署前备份：`/data/backups/nexora-20260729T025528Z.tar.gz`。
- 本机最新镜像 `sha256:6b907085...`：PASS；healthy、revision 0013、管理员保留、
  UID10001、非 privileged、0 devices。
- Snapshot 恢复定向回归：PASS；15 tests。
- 真实 Rocky Snapshot A/B/A 恢复：PASS；2 tests，36.91s，VM/磁盘无残留。
- `uv run pytest -q`：PASS；245 passed，9 opt-in skipped。
- Ruff、mypy：PASS；173 source files。
- Snapshot 恢复部署前备份：`/data/backups/nexora-20260729T041119Z.tar.gz`。
- 本机最新镜像 `sha256:960a36a1...`：PASS；healthy、revision 0013、管理员保留、
  UID10001、非 privileged、0 devices。
- VM 性能定向回归：PASS；7 tests。
- 真实 Rocky VM domstats：PASS；1 test，10.92s，只读且非负速率。
- `uv run pytest -q`：PASS；248 passed，10 opt-in skipped。
- Ruff、mypy：PASS；175 source files。
- VM 性能部署前备份：`/data/backups/nexora-20260729T041812Z.tar.gz`。
- 本机最新镜像 `sha256:c895bbf2...`：PASS；healthy、revision 0013、管理员保留、
  UID10001、非 privileged、0 devices。
- VM 性能版本部署后 Browser QA：PASS；375px 无横向溢出、页面或控制台错误。
- VM 创建 migration/契约/XML/服务/Web 定向回归：PASS；12 tests。
- 真实 Rocky managed qcow2 创建：PASS；1 test，19.42s；定义、启动和清理通过。
- `uv run pytest -q`：PASS；254 passed，11 opt-in skipped。
- Ruff format/check、mypy strict：PASS；184 source files。
- npm assets/audit、Compose、diff check：PASS；0 vulnerabilities。
- VM 创建 Browser QA：PASS；1280/375px、44px、无最终溢出或控制台错误。
- Browser QA 捕获并修复 4px gutter 溢出及已引用 Volume 候选泄漏。
- VM 创建部署前备份：`/data/backups/nexora-20260729T053325Z.tar.gz`。
- 本机镜像 `sha256:ffd381b1...`：PASS；healthy、revision 0014、管理员保留、
  UID10001、非 privileged、0 devices。
- VM 创建网络定向回归：PASS；15 tests，含 none/Bridge/libvirt Network。
- 真实 Rocky libvirt Network 创建：PASS；1 test，20.50s；MAC、启动、网络不变。
- `uv run pytest -q`：PASS；257 passed，11 opt-in skipped。
- VM 网络版本 Browser QA：PASS；375px、Network 候选、44px、无溢出或错误。
- VM 网络部署前备份：`/data/backups/nexora-20260729T055054Z.tar.gz`。
- 本机镜像 `sha256:87036ba4...`：PASS；healthy、revision 0014、管理员原值恢复、
  UID10001、非 privileged、0 devices。
- VM 创建本地 ISO 定向回归：PASS；16 tests，含 boot order 与 readonly SATA。
- 真实 Rocky 本地 ISO 创建：PASS；1 test，22.05s；启动和三资源清理通过。
- `uv run pytest -q`：PASS；258 passed，11 opt-in skipped。
- VM 本地 ISO Browser QA：PASS；375px、44px、无横向溢出或控制台错误。
- 本地 ISO 部署前备份：`/data/backups/nexora-20260729T060211Z.tar.gz`。
- 本机镜像 `sha256:66332ed5...`：PASS；healthy、revision 0014、管理员原值恢复、
  UID10001、非 privileged、0 devices。
- QA 临时管理员口令、Session 与临时文件复核：PASS；均已精确撤销或清理。
- 平台镜像创建定向回归：PASS；19 tests，含 migration、契约、服务与 Web。
- 真实 Rocky 平台 raw 复制后创建：PASS；1 test，21.28s；启动和零残留通过。
- `uv run pytest -q`：PASS；261 passed，12 opt-in skipped。
- Ruff format/check、mypy strict：PASS；194 source files。
- 平台镜像 Browser QA：PASS；375px、44px、无横向溢出或控制台错误。
- 平台镜像部署前备份：`/data/backups/nexora-20260729T062153Z.tar.gz`。
- 本机镜像 `sha256:300f0ff8...`：PASS；healthy、revision 0015、管理员原值恢复、
  UID10001、非 privileged、0 devices，HTTP 测试端口为 8002。
- Cloud Image 定向回归：PASS；16 tests，含文档、输入、XML、服务与 Web。
- 真实 Rocky NoCloud 创建与恢复：PASS；1 test，23.85s；三资源零残留。
- `uv run pytest -q`：PASS；264 passed，12 opt-in skipped。
- Ruff format/check、mypy strict：PASS；197 source files。
- Cloud Image Browser QA：PASS；375px、44px、无横向溢出或控制台错误。
- Cloud Image 部署前备份：`/data/backups/nexora-20260729T063948Z.tar.gz`。
- 本机镜像 `sha256:410d70ba...`：PASS；healthy、revision 0015、管理员原值恢复、
  UID10001、非 privileged、0 devices。
- Guest Agent 定向回归：PASS；6 tests，含解析、边界与认证 fragment。
- 真实 Rocky Guest Agent：PASS；1 test，14.40s；临时 Domain 零残留。
- `uv run pytest -q`：PASS；269 passed，13 opt-in skipped。
- Ruff format/check、mypy strict、diff check：PASS；199 source files。
- Browser QA 首次发现基础模板未加载 HTMX；补本地 htmx 2.0.4 后复验通过。
- Guest Agent Browser QA：PASS；XHR 200、375px、44px、无溢出或浏览器错误。
- Guest Agent 部署前备份：`/data/backups/nexora-20260729T065829Z.tar.gz`。
- 本机镜像 `sha256:b1b70db3...`：PASS；healthy、revision 0015、
  UID10001、非 privileged、0 devices；一次性 QA Session 已删除。
- ConsoleSession/串口/WebSocket 定向回归：PASS；11 tests。
- 真实 Rocky 串口：PASS；1 test，12.60s；主动关闭且远端零进程残留。
- `uv run pytest -q`：PASS；275 passed，14 opt-in skipped。
- Ruff format/check、mypy strict：PASS；205 source files。
- 串口 Browser QA：PASS；xterm、WebSocket、375px、44px、无错误或溢出。
- 串口部署前备份：`/data/backups/nexora-20260729T071404Z.tar.gz`。
- 本机镜像 `sha256:921bfe21...`：PASS；healthy、revision 0016、SQLite
  quick_check ok、UID10001、非 privileged、0 devices。
- VNC parser/websockify 定向回归：PASS；8 console tests。
- 真实 Rocky VNC：PASS；1 test，10.83s；经 Tunnel 读取 QEMU RFB banner。
- `uv run pytest -q`：PASS；277 passed，15 opt-in skipped。
- Ruff format/check、mypy strict：PASS；207 source files；npm 0 vulnerabilities。
- noVNC Browser QA：PASS；RFB connected/canvas、375px、44px、无错误或溢出。
- noVNC 部署前备份：`/data/backups/nexora-20260729T072854Z.tar.gz`。
- 本机镜像 `sha256:08913435...`：PASS；healthy、revision 0016、
  UID10001、非 privileged、0 devices；worker/Tunnel/Session 零残留。
- Remote relay：2 unit PASS；真实 Rocky 2 MiB、SHA-256 和零 partial PASS。
- 关机完整克隆定向：5 tests PASS；XML 未知项、manifest、页面和 relay。
- 真实 Rocky 完整克隆：1 test，25.47s；目标实际启动、源保留、零残留。
- `uv run pytest -q`：PASS；282 passed，17 opt-in skipped。
- Ruff format/check、mypy strict：PASS；217 source files。
- npm assets/audit、Compose、diff check：PASS；0 vulnerabilities。
- 克隆 Browser QA：375px 无溢出，44px 控件，无可编辑源/目标绝对路径。
- 部署前备份：`/data/backups/nexora-20260729T075902Z.tar.gz`。
- 本机镜像 `sha256:c4a18544...`：PASS；healthy、revision 0017、
  quick_check ok、管理员保留、UID10001、非 privileged、0 devices。
- Cloud 密码、静态 IPv4、扩容与恢复定向：PASS；21 tests。
- 真实 Rocky Cloud 创建：PASS；1 test，24.28s；raw 8→16 MiB、静态 seed、
  VM 启动，VM/Disk/seed/partial 零残留。
- `uv run pytest -q`：PASS；288 passed，17 opt-in skipped。
- Ruff format/check、mypy strict、npm assets/audit、Compose、diff：PASS；
  219 source files，0 vulnerabilities。
- Cloud Browser QA：PASS；1280/375px、22 可见控件最小 44px、无溢出或错误。
- 部署前备份：`/data/backups/nexora-20260729T082010Z.tar.gz`。
- 本机镜像 `sha256:2a94b911...`：PASS；healthy、revision 0018、
  quick_check ok、管理员保留、UID10001、非 privileged、0 devices。
- 网络拓扑定向：21 tests PASS；真实 Rocky 1 test，10.54s PASS。
- 网络拓扑 Browser QA：1280/375px、2 表、44px、无溢出/错误。
- 网络拓扑部署镜像 `sha256:7bb74594...`：healthy、非 privileged、0 devices。
- 审计读取/Web 定向：10 tests PASS；全量 294 passed、18 skipped。
- 审计 Browser QA：1280/375px、50 行、44px、无 HTML 注入或错误。
- 审计部署前备份：`/data/backups/nexora-20260729T084306Z.tar.gz`。
- 审计部署镜像 `sha256:51ee23e0...`：healthy、revision 0018、
  quick_check ok、UID10001、非 privileged、0 devices。
- 2026-08-05 只读门禁回滚验证：`uv run ruff check`、`ruff format`、`mypy` PASS
  （30 source files）；`uv run pytest -q tests/test_database.py tests/web/`
  PASS，数据库迁移链回到 `20260803_0022`，web 80 passed；无 `read_only` /
  `ensure_host_writable` 残留。

## Last Successful Commit

当前文档基线提交：`Establish Nexora documentation baseline`。
准确哈希以 `git log -1 -- PROJECT_STATUS.md` 为准，避免状态文件自引用提交哈希。

## Next Actions

1. 保持所有可导航产品页面由 React/Ant Design 接管的边界。
2. P9-002～010 已全部完成并部署生产；迁移链 head `20260803_0023`。
3. 具备隔离 IOMMU/`vfio-pci` 设备后执行 P7-006 最后一项真实验证。
4. 不开展 aarch64 或 Rocky 之外 RHEL 系验证。
5. 补充自动化测试缺口（XML 历史回滚、`needs_restart=True`、`is_attachable_volume`）。

## Resume Instructions

读取 `AGENTS.md`、本文件、P2-001、`SECURITY.md`、VM 创建设计和
`RESOURCE_SYNC_XML.md`。Snapshot 创建使用 revision 0013 独立 plan 与
`vm.snapshot_change` 三步任务；恢复仅允许配置等价的 current internal leaf，
且禁止 force/running/paused/reset-nvram。外部、非 leaf 和历史分支保持只读。
VM 导入使用 revision 0014、`vm.create` 三步任务和 Volume→VM 双锁；只接受未引用
managed Volume，不接受页面路径。可选网络和本地 ISO 同样只接受 Resource ID，
应用前重读远端权威状态。平台镜像使用 revision 0015、
`vm.create_from_media` 可恢复任务，复制校验后发现 Volume 再定义 VM。
Cloud Image 由固定 NoCloud 文档、计划 MAC 和受控 seed ISO 生成；无标准工具时
明确拒绝且不自动安装。
Guest Agent 只通过固定 `virsh qemu-agent-command --timeout 5` 读取；未配置、
停止和不可用均是正常展示状态，不自动进入客户机安装 Agent。HTMX 必须由本地
`static/vendor/htmx/htmx.min.js` 加载，不能退化为 CDN。
串口使用 revision 0016 和 `Sec-WebSocket-Protocol` 内的一次性 Token；服务端只
回显安全协议名，不回显 Token。浏览器关闭、超时、重启或节点移除必须关闭会话。
VNC 只接受无密码、回环 endpoint；通过 AsyncSSH local forward 和 Nexora 自有
单次 websockify worker 代理。不得重新引入会传递依赖 Redis 的 PyPI websockify。
Cloud Image 扩展使用 revision 0018 保存扩容后 SHA-256；页面明文密码立即转换为
SHA-512 crypt，计划、任务、日志和 seed 均不保存明文。静态 IPv4 只接受结构化
CIDR/gateway/DNS；恢复扩容必须同时验证目标 virtual size 与持久化 SHA。
完整克隆使用 revision 0017、`vm.clone` 和 `RemoteRelayTransfer`；源/目标路径只能
来自 Domain XML 与 Pool target。失败仅清理任务 partial，已发布文件供显式恢复；
带外碰撞、共享引用、backing chain、Host Device 或网络不兼容必须阻断。
真实入口见 `INTEGRATION_ENVIRONMENT.md`。

## Updated At

2026-08-06 Asia/Shanghai

## Updated By

OpenCode

> 2026-08-06 网络拓扑增强：修复节点颜色混淆（`vm_nic` 蓝、`virtual_machine` 深灰、
> `tap`/`veth` 独立浅色），支持 PCI 透传网卡展示（hostdev→pci_device 地址匹配，
> 生成 vm_nic 节点并关联 VM，提示"PCI 透传"）。已部署，kvm3 OpenWrt 2 个 I211
> 透传网卡验证通过。

> 2026-08-06 文档同步（审计报告整改）：ROADMAP P9-002~P9-010 标 DONE 并新增
> NEW-1~NEW-8 记录；PROJECT_STATUS 纠正"未部署"矛盾（P9-002~006 已于 2026-08-05
> 部署，镜像 `sha256:47f531f429e7`），迁移链 head 更新为 `20260803_0023`；补
> 测试缺口（XML 历史回滚、`needs_restart=True`、`is_attachable_volume`）。

> 2026-08-06 虚拟机操作闭环修复（审查 #1-#12）：修复运行中移除磁盘/网卡失败
> （detach 从 original XML 提取、网卡 update 改 update-device）、网卡更新按钮
> 必失败（改弹窗编辑）、本地 ISO 运行中热插拔（change-media --live）、CPU 拓扑
> 乘积改为 ≤（兼容热插拔余量）+ 前端联动约束 + max≤1024/threads∈{1,2}、
> 内存非法组合预检、添加光驱能力、运行中改 CPU/内存加提示、运行中磁盘 attach
> target 冲突预检。部署镜像 `nexora:rollback-fixops-20260806T113801Z` 保留。
> 验证：后端 437 passed、25 skipped；前端 21 tests + build；ruff/mypy 通过。

> 2026-08-06 创建虚拟机页面合并：`/vms/create` 单页内通过"磁盘来源"切换
> 已有系统盘 / 新建空盘 / 从平台镜像创建三种方式；创建空盘与平台镜像前必须
> 先选目标存储池；旧子路径保留并预选模式（删除了原独立子页面组件）。同步完成
> 全局密度收紧（按钮 32px、Card/表格/间距压缩）与挂载卷/选盘格式白名单
> （qcow2/qcow/raw/img，过滤 libvirt 误标 raw 的普通文件）。部署镜像
> `nexora:rollback-savecfg-20260805T101541Z` 之前保留，本次未另建回滚标签。

> 2026-08-05 配置直接保存 + XML 历史回滚 + 待重启标记：新增 `vm_xml_history` 表
> （0023，每 VM 10 份快照）与 save/rollback/history API；配置页每区块"保存"直接
> 创建任务（保留执行前重验），"历史版本"可回滚；运行中 VM 配置变更后显示"待重启"
> 标志（基于任务记录推断）。favicon 与布局对齐同步完成。部署镜像
> `nexora:rollback-savecfg-20260805T101541Z` 保留。

> 2026-08-05 VM 配置页与测试稳定：挂载卷显示占用（`used_by` 禁用挂载+悬浮说明）、
> 新增"新建卷"（Pool/名称/格式/容量→预检→任务）、配置区块收紧密度；移除三个 VM
> 渲染测试显式 10s 超时，全量前端 21 测试稳定通过（根因：vm creation plan 在 jsdom
> 下 8.5s，组合后超时）。部署镜像 `nexora:rollback-vmcfg-20260805T101541Z` 保留。

> 2026-08-05 页面头部统一：所有列表/详情页统一 `nx-detail-header`（标题+副标题左、
> 按钮右、`align="start"` 顶部对齐），有无副标题按钮位置一致；节点/虚拟机列表补
> 副标题。部署镜像 `nexora:rollback-header-20260805T101541Z` 保留回滚。前端全量
> 测试仍受既有资源累积型 flaky 影响（VM 创建预览/详情/配置渲染用例组合后拖慢后续
> 用例），已提升 `asyncUtilTimeout`/`testTimeout` 缓解并记录，待专项修复。

> 2026-08-05 过滤与拓扑统一：任务中心新增状态/节点过滤（`/internal/tasks` 补充
> host_id/host_name），审计过滤移到标题行右侧即选即查，虚拟机/任务/审计过滤统一
> `nx-filter-control` 模式；拓扑图颜色改为单一来源修复 VM 节点颜色与图例不符。
> 部署镜像 `nexora:rollback-filters-20260805T101541Z` 保留回滚。

> 2026-08-05 UI 一致性：补齐 `.nx-page-title` 头部样式（任务/审计/账户页标题布局
> 统一）、审计页分页改用 Ant Design Pagination、fact/metric 卡片视觉统一；部署镜像
> `nexora:rollback-uiuniform-20260805T101541Z` 保留回滚。前端全量测试存在既有 flaky
> （App.test.tsx 内 VM 详情/配置页渲染用例在全量串行下偶发失败、单独运行通过），
> 疑似文件内 async 泄漏（Cytoscape/Ant motion），已记录待专项修复；本次 UI 改动
> 构建通过、相关用例单独通过。

> 2026-08-05 能力探测修复：`command -v` 为 shell 内建，被 `env -- LC_ALL=C` 包装后
> 无法执行，导致全部工具探测假阴性（ubuntu2604-kvm 的 tool.virsh required_missing、
> 节点误标"能力受限"、无法创建虚拟机）。移除 env 包装后重新探测，节点恢复 ready、
> 全部工具 normal。镜像 `nexora:rollback-toolfix-20260805T101541Z` 保留回滚。

> 2026-08-05 网络标签可读化：节点类型/关系/告警映射中文，拓扑图悬浮显示详情，
> 表格列带悬浮提示并新增图例。前端测试 21 通过、构建通过；全量前端存在 2 个既有
> flaky 用例（VM 创建预览与旧 manage 地址，单独运行均通过，与本改动无关）。镜像
> `nexora:rollback-nettips-20260805T101541Z` 保留回滚。

> 2026-08-05 拓扑边修复：iproute2 JSON 的 master/link 为接口名而非 ifindex，导致
> vlan/bridge/vnet 之间无边。`_resolve_reference` 支持按名称关联，VLAN 的 link 纳入
> parent 解析；重扫 kvm1 后物理口→VLAN→Bridge→vnet→VM 链路完整建立。镜像
> `nexora:rollback-topolink-20260805T091423Z` 保留回滚。

> 2026-08-05 排查修复：kvm1 资源发现失败根因为 `tmp` 池含 `\xff` 非法字节卷名，
> `parse_volume_list` 严格解码抛异常。修复：替换解码容错 + 单个不可读卷跳过并告警
> （`storage_warnings`）。重新扫描 kvm1 成功：pools=7, volumes=64, interfaces=36,
> storage_warnings=10；网络拓扑按物理口→VLAN/Bridge→vnet→VM 分层显示。镜像
> `nexora:rollback-storagefix-20260805T084801Z` 保留回滚。

> 2026-08-05 UI：完成 P9-007 操作区与总览增强。VM 详情危险操作独立成行；总览增加
> 虚拟机状态分布、存储概况与任务排队；VM 列表支持状态/节点过滤。后端 pytest
> 426 passed、25 skipped，前端 20 tests 与构建通过。
>
> 2026-08-05 部署：P9-007 部署到生产。新镜像 `nexora:latest` = `sha256:69a6eaa02c17`
> （VM 危险操作分行、总览增强、VM 列表过滤），容器 healthy、监听 `0.0.0.0:8002`；
> DB revision 保持 `20260803_0022`（无 schema 变化），`quick_check` ok，登录页 200，
> 4 节点数据完整保留。回滚保留：镜像 `nexora:rollback-p9ui-20260805T074456Z`、
> 备份 `/data/backups/nexora-predeploy-20260805T074456Z.tar.gz`。

> 2026-08-05 部署：按确认部署最新版至生产。新镜像 `nexora:latest` =
> `sha256:47f531f429e7`（含 P9-002 空白磁盘、P9-003 关机迁移、P9-004 删除重命名、
> P9-005 网卡配置、P9-006 旧模板清理），容器 healthy、监听 `0.0.0.0:8002`；
> DB 迁移 `20260731_0020` → `20260803_0022` 成功（新建 `vm_blank_creation_plans`、
> `vm_remove_plans`），`quick_check` ok，登录页 200，4 节点数据完整保留。
> 回滚保留：镜像 `nexora:rollback-p9-20260805T070905Z`、备份
> `/data/backups/nexora-predeploy-20260805T070905Z.tar.gz`。

> 2026-08-05 更新：按确认不实现节点级只读门禁。实现后回滚 `Host.read_only`、
> 迁移 0023 与 `ensure_host_writable` 守卫（13 个 internal 写路由、40 处拦截），
> 回滚后 ruff/mypy PASS、web 80 passed、数据库迁移测试恢复通过，无残留。

> 2026-08-03 更新：完成 P9-002 空白磁盘 VM 创建（revision 0021）、P9-003 关机迁移
> （preserve_identity 保留 UUID/MAC）、P9-004 VM 删除与重命名（revision 0022）、
> P9-005 网卡 attach/detach/update。`uv run pytest -q` 为 428 passed、25 skipped，
> Ruff、Mypy 284 source files、React 20 tests 与生产构建均通过。旧兼容 POST 路由
> （P9-001）与旧模板清理（P9-006）仍待测试迁移后执行。

> 2026-07-29 更新：新增 Ubuntu 24.04 LTS nested KVM 接入、能力探测、已有 VM
> 自动发现与零残留销毁记录。

> 2026-07-31 更新：完成 P6-003 状态优先 UI。共享状态组件、全宽横向子系统、
> 渐进操作及安全格式化 XML 已落地；`uv run pytest -q` 为 366 passed、22 skipped，
> Ruff、Mypy、资产构建、npm audit、1280/375px Browser QA 与 diff check 均通过。

> 2026-07-31 部署：升级前一致备份为
> `/data/backups/nexora-20260731T081033Z.tar.gz`；旧镜像保留为
> `nexora:rollback-20260731-ui`。新 `nexora:latest` 为
> `sha256:24b6d693...64eae`，正式服务监听 `0.0.0.0:8002`，容器 healthy、
> revision 0020、SQLite quick_check ok、UID 10001、非 privileged、0 devices；
> 登录页 Browser QA 无溢出或控制台错误。

> 2026-07-31 P8-001：`uv run pytest -q` 为 374 passed、22 skipped；React 3 tests、
> Ruff、Mypy、两套 npm audit 和四断点 Browser QA 通过。部署备份为
> `/data/backups/nexora-20260731T094328Z.tar.gz`；正式镜像为
> `sha256:fc60f0cd...131d9`，旧镜像保留为 `nexora:pre-p8-001-20260731`。

> 2026-08-01 P8-002：`uv run pytest -q` 为 379 passed、22 skipped；React 5 tests、
> Ruff、Mypy、两套 npm audit 和三页面四断点 Browser QA 通过。部署备份为
> `/data/backups/nexora-20260801T051242Z.tar.gz`；正式镜像为
> `sha256:294b0573...e15f9f`，旧镜像保留为 `nexora:pre-p8-002-20260801`。

> 2026-08-01 P8-003：`uv run pytest -q` 为 383 passed、22 skipped；React 7 tests、
> Ruff、Mypy、两套 npm audit、legacy 资产构建和详情页四断点 Browser QA 通过。
> 统一固定语义 Token、无渐变/状态圆点/彩色 Tag 边框；UUID 详情由 React 接管，
> 原写操作保留在同源 `/manage/*`。UEFI 非安全启动测试继续通过。

> 2026-08-01 P8-003 部署：一致备份为
> `/data/backups/nexora-20260801T061004Z.tar.gz`；旧镜像保留为
> `nexora:pre-p8-003-20260801`。正式镜像为 `sha256:d47b59b5...94865`，服务监听
> `0.0.0.0:8002`，容器 healthy、SQLite quick_check ok、UID 10001、非 privileged、
> 0 devices 且运行时无 Node/npm；正式登录页无溢出、渐变、阴影或浏览器错误。

> 2026-08-01 P8-004 至 P8-006：`uv run pytest -q` 为 394 passed、22 skipped；
> React 13 tests、Ruff、Mypy、两套 npm audit、两套资产构建和四断点 Browser QA
> 通过。主页面、移动抽屉与任务深链接无横向溢出或浏览器错误；UEFI 非安全启动
> 在 managed Volume 与平台镜像两条创建流继续通过。

> 2026-08-01 P8 完整部署：一致备份为
> `/data/backups/nexora-20260801T075028Z.tar.gz`；旧镜像保留为
> `nexora:pre-p8-complete-20260801T154958`。正式镜像为
> `sha256:cbaefe74...52e885`，监听 `0.0.0.0:8002`，容器 healthy、SQLite
> quick_check ok、UID 10001、非 privileged、0 devices 且无 Node/npm；正式登录页
> 无溢出和浏览器错误，CSP nonce 与本地 manifest 资产正常。

> 2026-08-01 资源列表滚动条修复：移除全局 Ant Table 外层 `overflow-x:auto` 与
> 640px 最小宽度。多行节点/VM Browser QA 确认页面、外层和内容均无横向溢出。
> 修复镜像 `sha256:536bc2e0...55adcb` 已部署；备份为
> `/data/backups/nexora-20260801T081610Z.tar.gz`，回滚标签为
> `nexora:pre-scroll-fix-20260801T161556`，正式容器 healthy、quick_check ok。
