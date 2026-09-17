# Nexora Roadmap

状态：`TODO`、`ANALYZING`、`IN_PROGRESS`、`BLOCKED`、`REVIEW`、`DONE`、`DEFERRED`。

## P0：基础架构

| ID | 标题 | 状态 | 优先级 | 依赖 | 验收条件 | 涉及文件 | 测试要求 | 完成日期/备注 |
|---|---|---|---|---|---|---|---|---|
| P0-001 | 文档与架构基线 | DONE | 最高 | 无 | 权威文档、ADR、威胁模型和恢复入口落盘 | 根文档、`docs/` | 链接/占位/结构检查 | 2026-07-28 |
| P0-002 | Python 项目骨架 | DONE | 最高 | P0-001 | FastAPI 可启动，目录边界确定 | `pyproject.toml`, `src/`, `tests/` | 启动/导入测试 | 2026-07-28；9 tests |
| P0-003 | 单容器运行骨架 | DONE | 最高 | P0-002 | Tini、单 worker、非 root、healthcheck | Docker/Compose/entrypoint | 构建与无 KVM 启动 | 2026-07-28；容器健康 |
| P0-004 | SQLite 与 Alembic | DONE | 最高 | P0-002 | WAL、FK、超时、迁移和统一 Session | `db/`, `alembic/` | pragma/迁移/锁测试 | 2026-07-28；SQLite 验证 |
| P0-005 | 单管理员认证 | DONE | 最高 | P0-004 | 初始化、登录、改密、Session 撤销 | `auth/`, `web/` | 认证/CSRF/限速 | 2026-07-28；29 tests + Browser QA |
| P0-006 | 凭据加密 | DONE | 最高 | P0-004 | AEAD、AAD、key version、fail closed | `security/` | 加密/篡改/轮换 | 2026-07-28；AES-256-GCM |
| P0-007 | SSH Host Key 流程 Spike | DONE | 最高 | P0-002 | 首次确认、历史显示、变化阻断 | `docs/spikes/`, `remote/` | 临时 sshd 集成测试 | 2026-07-28；真实 sshd PASS |
| P0-008 | RemoteExecutor | DONE | 最高 | P0-006,P0-007 | typed adapter、超时、限额、取消、审计 | `remote/` | 注入/超时/脱敏 | 2026-07-28；真实 SSH PASS |
| P0-009 | 任务 lease Spike | DONE | 最高 | P0-004 | 原子领取、续租、崩溃识别 | `docs/spikes/`, `tasks/` | 并发/重启/锁测试 | 2026-07-28；原子 claim |
| P0-010 | 持久化任务系统 | DONE | 最高 | P0-008,P0-009 | 步骤、心跳、检查点、恢复和取消 | `tasks/`, `web/` | 状态机/恢复测试 | 2026-07-28；任务中心 |
| P0-011 | Tabler 页面骨架 | DONE | 高 | P0-005 | 浅色主题、导航、技术字体和错误处理 | `templates/`, `static/` | 页面/可访问性冒烟 | 2026-07-28；Browser PASS |
| P0-012 | XML 保留 Spike | DONE | 最高 | P0-002 | 安全解析、局部修改、规范化 hash | `docs/spikes/`, `xml/` | 未知元素/XXE/Diff | 2026-07-28；11 tests |
| P0-013 | P0 部署运维文档 | DONE | 高 | P0-003,P0-010 | 部署、升级、备份、恢复、回滚、排障 | `docs/operations/` | 文档命令演练 | 2026-07-28；恢复演练 PASS |

## 后续阶段

| ID | 标题 | 状态 | 依赖 | 核心验收 |
|---|---|---|---|---|
| P1-001 | 节点接入与能力探测 | DONE | P0 | Rocky 9.7（RHEL 系）/Debian 13/Ubuntu 24.04 LTS/Ubuntu 26.04 LTS（长期全功能）PASS |
| P1-002 | 全量资源发现与索引 | DONE | P1-001 | Rocky/Ubuntu 已有 VM/Pool 真实发现 PASS |
| P1-003 | 带外变更与零残留移除 | DONE | P1-002 | 真实移除零残留 PASS，Ubuntu 节点验证通过 |
| P2-001 | Cockpit Machines VM 基线 | DONE | P1 | 2026-07-30；全部 VM 基线功能完成，含 24h 性能历史 schema |
| P3-001 | 媒体 Range 与镜像复制 | DONE | P1 | 2026-07-28；177 tests + Rocky/KVM 集成 PASS |
| P3-002 | dir 与 NFS netfs Pool | DONE | P1 | 2026-07-28；真实 NFS 生命周期与数据保留 PASS |
| P3-003 | dir/netfs Storage Volume | DONE | P3-002 | 2026-07-29；dir/netfs 创建、扩容、引用阻断、删除与零残留 PASS |
| P4-001 | 网络只读发现与拓扑 | DONE | P1 | 2026-08-03；修复真实 ID 边映射与链路状态语义，响应式 Cytoscape/表格 QA PASS |
| P4-002 | Bridge/VLAN 安全写入 | DONE | P4-001 | 2026-07-30；Bridge/VLAN 创建、回滚脚本、确认期限、预检、任务流程完成 |
| P5-001 | 高级 VM/XML 配置 | DONE | P2 | NUMA/CPUTune/Watchdog/vsock 只读展示 + NUMA/CPUTune 写入完成 |
| P5-002 | 克隆与关机迁移 | DONE | P2,P3 | 2026-07-30；关机完整克隆及 Rocky->Ubuntu 跨节点双机实测 PASS |
| P6-001 | 产品化与兼容验证 | DONE | P1-P5 | 2026-07-30；发行版矩阵、安全审计、性能验证、产品化文档完成 |
| P6-002 | 现代明亮彩色 UI 升级 | DONE | P0-011 | 2026-07-29；鲜活 Token、统一组件、AA 对比度、四断点及最终双断点 Browser QA PASS |
| P6-003 | 状态优先工作台现代化 | DONE | P6-002 | 2026-07-31；状态摘要、全宽横向子系统、渐进操作和格式化 XML；1280/375px Browser QA PASS |
| P7-001 | 24h VM 指标与节点性能 | DONE | P2,P6 | 2026-08-01；有界采样、查询、页面、失败降级及 Rocky VM/Host 实测 PASS |
| P7-002 | 高级设备 XML 写入 | DONE | P5-001 | 2026-07-31；Watchdog、vsock、CPU cache/maxphysaddr 安全写入完成 |
| P7-003 | PCI/USB Host Device 直通 | DONE | P7-002 | 2026-07-31；关机门禁、IOMMU/vfio、设备锁和执行前重验完成 |
| P7-004 | virtiofs/9p 共享目录 | DONE | P7-002 | 2026-08-01；授权根、共享内存、写后规范化及 Rocky virtiofs 实测 PASS |
| P7-005 | Cloud Image 静态 IPv6 | DONE | P2-001 | 2026-08-01；Rocky IPv6-only/双栈复制、seed、启动和零残留 PASS |
| P7-006 | P7 产品化收尾 | BLOCKED | P7-001..005 | 2026-08-01；指标/目录/IPv6 PASS；节点无 IOMMU group/vfio-pci，设备实测受硬件阻塞 |
| P8-001 | React/Ant Design 基础平台 | DONE | P6-003 | 2026-07-31；认证预览、CSP nonce、manifest、四断点 QA 与正式部署 PASS |
| P8-002 | 核心只读页面迁移 | DONE | P8-001 | 2026-08-01；总览、节点和 VM 列表、分页、四断点 QA 与正式部署 PASS |
| P8-003 | 资源详情迁移 | DONE | P8-002 | 2026-08-01；节点/VM 详情、指标、Guest Agent、XML、快照、设备、兼容管理入口和四断点 QA PASS |
| P8-004 | 创建与变更迁移 | DONE | P8-003 | 2026-08-01；节点接入、两类 VM 创建、生命周期、存储、媒体与 Bridge/VLAN 变更进入 React 闭环 |
| P8-005 | 运维页面迁移 | DONE | P8-004 | 2026-08-01；任务、审计、设置、React 串口/VNC 与 Cytoscape 拓扑完成 |
| P8-006 | 旧前端收敛清理 | DONE | P8-005 | 2026-08-03；16 个主/详情路由桌面与移动真实数据巡检 PASS；仅保留认证与 `/manage/*` 配置兼容岛 |
| P8-007 | 节点硬件与能力可读化 | DONE | P8-003 | 2026-08-03；硬件、实体网卡 MAC、功能支持和刷新闭环完成；Rocky/双断点 QA PASS |
| P8-008 | VM 操作区紧凑布局 | DONE | P8-003 | 2026-08-03；7 个操作按钮 36px/8px 间距，1280/375px 无重叠或溢出 |
| P8-009 | VM 直通设备可视化 | DONE | P8-003,P7-003 | 2026-08-03；关联 PCI 资源，展示设备名称、地址、驱动和 IOMMU 组；kvm3/OpenWrt 双断点 QA PASS |
| P8-010 | 全站 React 页面收敛 | DONE | P8-006 | 2026-08-03；认证、VM 配置和历史 manage 地址均由 React/Ant Design 接管；生产数据双断点 QA PASS |
| P8-011 | 节点 PCIe 直通能力展示 | DONE | P7-003,P8-007 | 2026-08-03；按 IOMMU/vfio-pci 判定支持状态，kvm3 显示 2 个可直通设备 |
| P8-012 | 节点导航图标语义优化 | DONE | P8-002 | 2026-08-03；顶部节点入口改用 Ant Design CloudServerOutlined，前端测试与构建 PASS |
| P8-013 | 镜像图标与字体偏好收敛 | DONE | P8-012 | 2026-08-03；镜像入口改用 FileImageOutlined，固定舒适密度与系统 UI 字体，技术字段统一等宽 Token |
| P8-014 | 管理员时区统一显示 | DONE | P8-013 | 2026-08-03；全部 React 时间按账户时区格式化，无偏移 SQLite 时间按 UTC 解析，UTC+8 回归 PASS |
| P8-015 | 存储配置流程文案可读化 | DONE | P8-014 | 2026-08-03；“预览计划/创建任务”统一为“检查创建配置/确认并执行”，组件回归 PASS |
| P9-001 | internal JSON 写入契约与零 Jinja 护栏 | DONE | P8-015 | 2026-08-03；兼容契约测试全部迁移到 internal JSON API，旧兼容 POST 路由已注销 |
| P9-002 | 节点优先 VM 创建与空白磁盘 | DONE | P9-001 | 2026-08-03；空白 qcow2/raw Volume 同任务创建并定义 VM，revision 0021，可恢复执行与权威验证 PASS |
| P9-003 | 快照、克隆、关机迁移与自动启动 React 化 | DONE | P9-001 | 2026-08-05；快照、克隆、自动启动、关机迁移（保留 UUID/MAC）完成并部署生产 |
| P9-004 | VM 删除与重命名 | DONE | P9-003 | 2026-08-05；undefine/磁盘/NVRAM 逐项选择、关机 domrename、名称确认与权威验证完成并部署 |
| P9-005 | VM 网卡完整配置 | DONE | P9-003 | 2026-08-05；attach/detach/update、MAC 与网络切换、live/config 门禁完成并部署 |
| P9-006 | 旧业务模板与路由清理 | DONE | P9-001..005 | 2026-08-05；17 个旧 POST 路由文件与 55 个业务模板已删除，仅保留 react_shell.html |
| P9-007 | VM 操作区危险操作分行与总览增强 | DONE | P8-008 | 2026-08-05；强制操作/删除独立危险操作行，总览增加虚拟机分布、存储与任务排队，VM 列表支持状态/节点过滤 |
| P9-008 | VM 配置每区块直接保存 + XML 历史与回滚 | DONE | P9-001..005 | 2026-08-05；`vm_xml_history`（0023，每 VM 10 份）、save/history/rollback API、`vm.xml_restore` 三步 handler、待重启标记（`needs_restart`） |
| P9-009 | 创建虚拟机页面三源合并 | DONE | P9-002 | 2026-08-06；`/vms/create` 单页"磁盘来源"切换已有系统盘/空盘/平台镜像，旧子路径预选模式 |
| P9-010 | VM 操作闭环修复（审查 #1-#12） | DONE | P9-005,P9-008 | 2026-08-06；live detach 断链、网卡更新弹窗与 update-device、本地 ISO 热插拔、CPU 拓扑 ≤ 校验+前端联动、添加光驱、内存组合预检、target 冲突预检 |
| NEW-1 | 挂载卷格式白名单（qcow2/qcow/raw/img） | DONE | P9-008 | 2026-08-06；`is_attachable_volume` 统一挂载/创建/扩容校验，过滤 libvirt 误标 raw 的普通文件 |
| NEW-2 | 全局界面密度收紧 | DONE | P8-008 | 2026-08-06；按钮 32px、表格内边距 10px、页面间距 12px |
| NEW-3 | 网络拓扑层级化 + 名称引用边解析 | DONE | P4-001 | 2026-08-05；物理口→VLAN→Bridge→vnet→VM，`_resolve_reference` 名称关联 |
| NEW-4 | 节点能力探测工具检测修复 | DONE | P1-001 | 2026-08-05；`command -v` 不再被 `env` 包裹，工具探测恢复 |
| NEW-5 | 网络拓扑标签可读化 + 单一数据源图例 | DONE | P4-001 | 2026-08-05；`networkLabels.ts` 中文映射、`nodeTypeColor` 单一来源 |
| NEW-6 | 存储发现容错（非法 UTF-8 卷名跳过告警） | DONE | P3-003 | 2026-08-05；`errors="replace"` + `storage_warnings`，kvm1 重新扫描成功 |
| NEW-7 | 等待重启标记 `needs_restart` | DONE | P9-008 | 2026-08-05；任务时序推断，列表/节点/详情展示"待重启" |
| NEW-8 | favicon 与布局对齐 | DONE | P8-015 | 2026-08-05；`/static/favicon.svg`、`nx-detail-header` 统一 |
| NEW-9 | 网络拓扑透传网卡展示 + 节点颜色区分 | DONE | NEW-3 | 2026-08-06；hostdev PCI→pci_device 地址匹配生成 vm_nic 节点并关联 VM，`vm_nic`/`virtual_machine` 分色；kvm3 OpenWrt 2 个 I211 透传验证 |
| NEW-10 | 前端视觉一致性与联动逻辑审计整改 | DONE | NEW-2 | 2026-08-07；Alert title/主按钮/表格响应式/共享组件/标题包裹/筛选 URL 持久化/任务返回/轮询健壮性/弹窗宽度，部署 `nexora:noratelimit-20260807T154034Z` |
| NEW-11 | 移除登录限流 | DONE | NEW-10 | 2026-08-07；移除失败次数锁定与 429 分支，保留登录审计记录；SECURITY.md 同步 |
| NEW-12 | 存储页面节点维度管理 | DONE | P8-015 | 2026-08-10；顶部节点选择器（默认全部节点），选定后池/卷表仅显示该节点资源，创建池节点自动带入选定节点，创建卷目标 Pool 仅列该节点 active managed 池；前端 23 tests + 部署验证 |
| NEW-13 | 存储卷展示过滤与使用状态 | DONE | NEW-12 | 2026-08-10；过滤 libvirt 误标 raw 的普通文件（如 openwrt.xml），仅展示磁盘镜像与光驱 ISO（`is_display_volume`）；卷状态改为基于 VM 引用的"使用中/未使用"，只读卷保留只读提示；后端 465 tests + 部署验证 |
| NEW-14 | 顶部品牌 Logo 比例与透明背景修复 | DONE | NEW-10 | 2026-08-12；改用用户提供的透明 PNG，Logo 仅固定高度、宽度按原始比例自适应；桌面/移动品牌字标比例与间距统一，前端 24 tests + 双断点 Browser QA + 生产部署验证 PASS |
| NEW-15 | 全站深度视觉 QA 与双主题 | DONE | NEW-14 | 2026-09-16；Light/Dark 持久化、公共布局与弹层约束、移动媒体 Card、技术字段省略、兼容配置路由修复；25 路由×10 Light 视口 + Dark 桌面/移动回归、构建与生产部署 PASS，镜像 `sha256:01fcfc60...ef73c74` |
| NEW-16 | 管理员密码最低长度调整 | DONE | NEW-15 | 2026-09-16；初始化与账户改密最低长度统一为 8，前后端测试与安全文档同步；认证测试 20、前端测试 26、构建/审计/部署验证 PASS，镜像 `sha256:422a03e3...c396a41` |

P7 暂不包含 aarch64、Rocky 之外的 RHEL 系发行版、在线迁移、任意历史分支恢复、
复杂 external/raw/block/network Snapshot 链及 Bond/OVS/VXLAN 写入。

## 2026-09-16 E2E 缺口跟踪

当前 `kvm2` 自动发现与主页面覆盖已完成，但本轮 Autonomous Web E2E 状态为
`completed_with_gaps`，详见 `.e2e/final-report.md`。后续恢复入口按优先级为：

1. DONE（2026-09-17）：修复并回归 FAIL-001；高级 Watchdog/vsock 表单从当前 XML 回填，且兼容
   Watchdog model 不得在未明确选择时被删除。
2. DONE（2026-09-17）：修复并回归 FAIL-002；账户表单校验拒绝留在表单显示字段错误。
3. 准备明确隔离的关机 VM/存储夹具后，执行 VM 配置 apply → 刷新/重新进入 → XML/列表
   校验 → rollback，以及创建/快照/克隆/删除完整生命周期。
4. 准备可取消的长任务与 interrupted 任务夹具，补测任务取消和显式恢复；具备第二个
   ready 节点后补测跨节点迁移。

详细阶段范围以 `docs/product/SCOPE.md` 为准。开始任务时将对应行改为
`ANALYZING` 或 `IN_PROGRESS`，结束时填写准确日期与结果。

## 2026-09-17 修复复测

FAIL-001/FAIL-002 已修复并在 `nexora:latest` `sha256:ff2a77189e432348e1fa9da8499bac63aa4f841f9510d684e7f69222df3b14fd` 上通过浏览器复测。剩余缺口仍是安全夹具不足导致的 VM 配置真实 apply/回滚、创建删除生命周期、任务取消/恢复和多节点迁移，不因本次修复标记为完成。
