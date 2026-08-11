# Changelog

本项目遵循 Keep a Changelog 的结构；版本发布前再确定正式版本号。

## Unreleased

### Added

- 存储卷展示过滤与使用状态：libvirt 会把普通文件（如 `openwrt.xml`）探测成 raw，
  现新增 `is_display_volume`（磁盘镜像 + 光驱 ISO 白名单）过滤非存储卷实体；卷状态
  由"已纳管/只读"改为基于 VM 磁盘引用的"使用中/未使用"，只读卷保留只读提示与
  操作禁用。
- 存储页面节点维度管理：顶部新增节点选择器（默认"全部节点"），选定节点后存储池
  与存储卷表仅显示该节点资源；创建存储池时节点自动带入选定节点（下拉禁用），创建
  存储卷时目标 Pool 下拉仅列出该节点的 active managed Pool。

### Fixed

- 移除登录限流：删除失败次数锁定（`MAXIMUM_FAILURES`/`LOGIN_WINDOW`/
  `LoginRateLimitedError`/`_failure_count`）与登录 429 分支，连续输错密码不再被
  临时锁定；登录历史审计记录（`LoginAttempt`）继续保留。
- 前端 Alert 属性统一为 antd v6 标准的 `title`（`message` 已弃用），`showIcon`
  全部显式声明；主按钮统一使用 `type="primary"`；14 处表格补齐
  `nx-responsive-table` 响应式适配。
- 前端视觉一致性：提取共享 `FactCard`/`formatBytes` 组件消除 5 处重复定义，
  统一 `.nx-metric-grid`，8 处页面标题补齐 `.nx-page-title` 包裹，预览确认类
  弹窗统一宽度。
- 联动逻辑：列表筛选状态持久化到 URL query（虚拟机/审计/任务/网络），任务完成
  后支持"返回源页面"（sessionStorage 记录来源），任务详情轮询改为 AbortController
  并在请求失败后停止、支持重试。
- 网络拓扑修复节点颜色混淆并支持透传网卡展示：`vm_nic` 与 `virtual_machine` 之前
  同色难以区分，现分别使用品牌蓝与深灰；新增 `tap`/`veth` 独立浅色。同时将
  虚拟机透传的 PCI 网卡（`hostdev type=pci`）纳入拓扑：按 PCI 地址匹配节点资源，
  生成 `vm_nic` 节点（label 为 PCI 地址 + 设备名），挂到所属虚拟机并显示
  "PCI 透传"提示。已验证 kvm3 上 OpenWrt 透传的 2 个 I211 网卡正确展示。

### Fixed

- 修复运行中 VM 移除磁盘/网卡失败的 bug：live detach/update 之前从“变更后的
  proposed XML”中提取设备片段，而 detach 已把设备删除，导致必然找不到设备并报
  “not found”。现在 detach 从 original XML 提取，网卡 update 改用 `virsh
  update-device --live --persistent` 原位替换（之前错误地走 attach-device）。
- 修复网络接口“更新”按钮必然失败的问题：旧实现把 `new_mac` 设为与当前 MAC 相同，
  被 `InterfaceUpdateChange` 的“新 MAC 必须不同”校验拒绝；现在改为弹窗编辑
  网络/型号/新 MAC，仅提交实际变更字段。
- 修复运行中 VM 挂载/弹出本地 ISO 只改持久化配置、运行域不生效的问题：本地 ISO
  变更现在对运行中的 VM 使用 `virsh change-media --live --persistent` 即时生效；
  平台/缓存 ISO 继续要求关机（凭据绑定与校验语义）。
- CPU 拓扑校验从“乘积必须等于最大 vCPU”放宽为“乘积不得超过最大 vCPU”，兼容合法
  的热插拔余量配置（`vcpu` > 拓扑乘积）；并新增 maximum_vcpus ≤ 1024、
  threads ∈ {1,2} 约束，前端同步联动提示与上限。
- 内存配置预检新增非法组合拦截：discard 配 anonymous 后备、file 后备配 private
  访问模式会在预览阶段报错，而不是执行时才失败。
- 运行中 VM 保存 CPU/内存/高级配置时新增明确提示（重启后生效），磁盘/网卡/光驱
  热插拔即时生效。

### Changed

- 新增“添加光驱”能力：VM 无光驱设备时可新建空 CD-ROM（sata 总线并自动补
  controller），挂载列表随之为空托盘。
- 运行中挂载磁盘时，若目标盘符已被运行域 transient 设备占用，预检阶段即报错提示
  重启，而不是执行 attach 失败。
- 创建虚拟机页面合并为单一页面：在 `/vms/create` 内通过“磁盘来源”切换“已有系统盘 /
  新建空盘 / 从平台镜像创建”三种方式，不再需要跳转到独立子页面；创建空盘和从平台
  镜像创建前必须先选择目标存储池。原 `/vms/create/blank-disk` 与
  `/vms/create/platform-image` 路径保留并预选对应模式。
- 全局界面密度调整：按钮高度从 44px 收紧到 32px、Card 内边距与表头高度收紧、表格
  单元格垂直内边距 14px 收至 10px、页面纵向间距统一为 12px，降低行高与页面稀疏感。
- 挂载存储卷与创建虚拟机选择磁盘时，只允许真正的磁盘镜像文件（qcow2/qcow/qcow1/
  raw/img 扩展名），过滤 libvirt 误标为 raw 的普通文件（如 .tar.gz、.xml）。

### Fixed

- 将存储池和存储卷创建流程中的“预览计划、审查计划、创建任务”技术术语统一改为
  “检查创建配置、检查存储配置、确认并执行”，底层预检、Diff、确认和任务队列不变。
- 修复 React 页面忽略管理员时区并直接使用浏览器时区的问题；节点同步、任务、审计、
  登录历史和媒体凭据时间统一按账户时区显示，无偏移 SQLite ISO 时间明确按 UTC 解析。
- 将顶部导航“镜像”入口从图片素材图标改为文件镜像图标；移除作用有限的页面密度和
  全局等宽字体选项，普通界面使用浏览器系统 UI 字体，技术字段统一使用无连字的
  本机等宽字体 Token。
- 将顶部导航“节点”的拓扑关系图标替换为服务器图标，使入口更准确表达 KVM 计算节点
  与宿主机语义，并保持现有导航尺寸、颜色和交互不变。
- 修复 VM 详情 API 丢弃 Domain XML `host_devices` 的问题；现在按同节点 PCI 地址关联
  资源索引，OpenWrt 等使用网卡直通的虚拟机可查看设备名称、PCI 地址、驱动和
  IOMMU 组，网络子系统会单独统计透传网卡。
- 修复虚拟机详情操作按钮受全局 44px 高度影响而在窄空间发生边框重叠的问题；操作区
  改为 36px 紧凑按钮和 8px Flex 换行间距，桌面与移动端均保持独立按钮边界。
- 修正节点能力探测扩展后任务仍声明 19 步导致后续检查点失败的问题；手动刷新现在
  同时更新能力、硬件和资源索引，并过滤 veth、Docker 与非管理虚拟 Bridge。
- 修复 React 网络拓扑把显示名称误作 Cytoscape 节点 ID 导致真实关系边初始化失败、
  `/networks` 内容区空白的问题；接口改用 `operstate`、VM/NIC 改用运行态展示状态。
- 修复总览子系统描述选择器覆盖状态 Tag 文字色的问题，所有状态 Tag 继续使用统一
  浅亮无边框 Token；网络、VM 详情、任务和节点详情表格补齐无横向滚动的响应式布局。
- 为 virtiofs 自动补齐 `memfd`/shared memory backing，并在卸载最后一个 Nexora
  virtiofs 设备时仅清理本次新增内容；写后校验兼容 libvirt 的设备排序和自动 PCI
  address，同时继续拒绝任何无关 Domain XML 变化。
- 移除 React 页面全局表格外层的强制横向滚动与最小宽度，节点和虚拟机页面仅在
  内容真实溢出时由组件自身滚动，不再显示无意义滚动条。

### Added

- 增加 VM 配置统一 internal JSON 预览/确认接口，React 不再解析旧 HTML；快照创建、删除、
  恢复、关机完整克隆、自动启动、存储池移除及存储卷扩容/删除均进入 React 操作闭环。
- VM 创建向导增加显式目标节点选择，系统盘、网络和 ISO 在节点确定后按同节点过滤。
- 新增空白磁盘 VM 创建：在同一可恢复任务中先创建 qcow2/raw 空白存储卷再定义虚拟机，
  含权威预检、XML Diff、确认令牌与写后验证；新增 `/vms/create/blank-disk` React 页面
  和 internal `/vm-create/blank-disk/*` 接口，并新增 revision 0021 计划表。
- 新增关机迁移：在克隆基础设施上提供 `preserve_identity` 模式，迁移保留源 UUID 与
  MAC、复制全部磁盘与 NVRAM、在目标节点定义并验证；默认保留源定义与磁盘，源端清理
  保持为独立危险操作；VM 详情页新增关机迁移入口和 internal `/migrate/*` 接口。
- 新增 VM 删除与重命名：删除默认仅 `virsh undefine`，磁盘与 NVRAM 可逐项选择并需名称
  确认；重命名使用关机 `virsh domrename` 并做权威验证；新增 internal `/remove/*` 接口、
  React 删除/重命名弹窗和 revision 0022 计划表。
- 新增网卡完整配置：支持网卡 attach、detach、update（MAC、Bridge/libvirt Network 切换、
  型号），复用 `VmChangePlan` 三步任务与 live/config 安全门禁；VM 配置页新增"网络接口"
  区块和 `xml/network.py` 结构化变换。
- VM 详情操作区将强制关机/强制重启与删除归入独立的"危险操作"行，与常规操作分隔，
  降低误触风险；常规操作保持 36px 紧凑按钮。
- 总览页增加虚拟机状态分布（运行/暂停/停止）、存储概况（池/卷）与任务排队信息，
  子系统状态新增"存储"和"任务"行。
- 虚拟机列表支持按运行状态（运行中/已暂停/已停止）与节点过滤，过滤条件与服务端分页
  协同；`/internal/vms` 新增 `state`、`host_id` 查询参数。
- 网络拓扑图改为按层级定位：物理网卡在最底层，向上依次为 VLAN、Bridge、vnet/tap、
  VM 网卡与虚拟机，取代力导向"孤岛圆"布局。
- 修复网络拓扑边缺失：iproute2 JSON 的 `master`/`link` 为接口名称而非 ifindex，
  `_resolve_reference` 现在支持按名称关联 master/parent，VLAN 的 `link`（下层设备）
  也纳入 parent 解析；物理口→VLAN→Bridge→vnet→VM 完整链路得以建立。
- 网络拓扑标签可读化：节点类型、关系与告警统一映射中文（如 "桥接端口"、"MTU 不一致"），
  拓扑图悬浮节点/连线显示类型、关系与告警说明，表格状态/标记/风险列带悬浮提示，
  并新增节点类型图例。
- 存储发现容错：`parse_volume_list` 改用替换解码容忍非法 UTF-8 卷名；单个卷
  `vol-dumpxml` 或解析失败时跳过并计入任务告警，不再中断整次资源发现，保证后续
  接口发现等步骤继续执行。
- 修复节点能力探测工具检测：`command -v` 是 shell 内建，原实现被 `env -- LC_ALL=C`
  包装后无法执行导致全部工具误报缺失（`tool.virsh` 等 required_missing，节点误标
  "能力受限"）；工具探测移除 env 包装后恢复正常，受影响节点重新探测即恢复 ready。
- 界面布局一致性：补齐 `.nx-page-title` 头部样式，统一任务/审计/账户页标题布局；
  审计页分页改用 Ant Design Pagination（与其他列表页一致）；`nx-fact-card` 与
  `nx-metric-grid` 卡片高度、数值字号统一。
- 列表页过滤控件统一：任务中心新增状态/节点过滤（`/internal/tasks` 返回
  `host_id`/`host_name`），审计页过滤移到标题行右侧并改为即选即查，虚拟机列表过滤
  同步使用统一 `nx-filter-control` 宽度；均采用"标题行右侧 Select"模式。
- 网络拓扑图颜色与图例统一：节点类型颜色改为单一来源（`nodeTypeColor`），修复图上
  VM 节点因类型键名错误显示灰色、与图例不符的问题。
- 页面头部统一：所有列表与详情页统一为 `nx-detail-header`（标题+副标题在左，操作
  按钮/过滤在右），按钮与标题顶部对齐（`align="start"`），有无副标题均保持一致；
  节点/虚拟机列表页补充副标题说明。
- VM 配置页增强：挂载卷列表展示占用状态（`used_by`），被虚拟机使用的卷禁用挂载并
  悬浮说明（防止数据损坏）；新增"新建卷"入口（选 Pool/名称/格式/容量 → 预检 →
  创建任务）；配置区块间距收紧提高信息密度。
- VM 配置改为"每区块直接保存"：保存按钮不再强制展示 Diff，提交即创建任务（仍走
  执行前资源版本校验）；新增 `vm_xml_history` 表（每 VM 保留最近 10 份配置前 XML
  快照）与"历史版本"入口，可选中历史快照回滚（`vm.xml_restore` 任务执行
  校验/define/刷新）。
- 等待重启标记：VM 运行中若最近成功配置变更任务晚于最近成功启动任务，则在虚拟机
  列表、节点详情与 VM 详情显示"待重启"标志（悬浮说明），提示配置修改需重启生效。
- 布局对齐：节点/虚拟机列表表格纳入 Card；存储/账户/复制/预览页头部统一
  `nx-detail-header`；创建页头部间距统一。
- 新增浏览器标签页 favicon（`/static/favicon.svg`）。
- 前端测试稳定化：移除三个 VM 渲染测试的显式 10s 超时（改用全局 20s），解决
  jsdom 下表单交互慢导致的资源累积型偶发失败，全量前端测试稳定通过。

### Removed

- 注销全部旧兼容 Jinja POST 路由：29 个兼容契约测试已迁移到 internal JSON API，旧的
  CPU/内存/磁盘/CD-ROM/克隆/快照/平台 ISO/存储/网络/媒体/控制台等 POST 路由不再注册。
- 删除 17 个旧 POST 路由文件与 55 个业务模板，页面模板仅保留 `react_shell.html`；
  控制台 WebSocket 桥接提取到独立的 `web/routes/console_socket.py` 继续注册。
- 前端 React 页面直接使用 `/internal/*` JSON API 读取 Guest Agent、性能指标与 VM 详情，
  移除依赖旧 Jinja 片段的读取路径。

- 节点功能支持增加“PCIe 设备直通”，依据已扫描 PCI 设备的 IOMMU Group 与
  `vfio-pci` 绑定状态展示支持、需关注或不支持，并显示当前可直通设备数量。
- React/Ant Design 接管初始化、登录和完整 VM 配置入口；CPU、内存、磁盘、光驱、
  PCI/USB、共享目录与高级设备继续复用原有 Diff、确认和任务安全链，历史
  `/manage/*` 地址返回同一 React Shell。
- 节点详情增加用户可读的功能支持、硬件概览和实体网卡列表，展示厂商、型号、CPU、
  内存、NUMA、链路用途与 MAC；不采集主机、磁盘序列号或其他硬件唯一标识。
- 增加 React 19、TypeScript、Vite 与 Ant Design 6 基础平台、认证 `/ui-preview`
  Shell、内部 Session API、CSP nonce 和 fail-closed Vite manifest 资产加载。
- 增加双前端多阶段容器构建；运行镜像继续保持单 Uvicorn worker 且不含 Node/npm。
- React 接管总览、节点列表和虚拟机列表，增加分页内部 API、状态优先总览、桌面
  Ant Design Table、移动 Card、中文浅亮无边框状态和 Session 显示偏好同步。
- React 接管 UUID 节点和 VM 详情，增加节点指标、24h VM 指标、Guest Agent、
  设备、快照和安全格式化 XML；旧写操作保留在同源 `/manage/*` 兼容入口。
- React 接管 managed Volume VM 创建，增加受限资源选项 API、原地 Domain XML
  Diff 与确认任务；UEFI 和 Secure Boot 独立配置，支持 UEFI 非安全启动。
- React 接管 Host Key 两阶段节点接入与平台镜像 VM 创建，保留指纹变化阻断、凭据
  不回显、复制校验、Cloud-init、grow-only 扩容和可恢复任务；平台创建新增 UEFI
  非安全启动、Secure Boot、TPM 与 Driver ISO 权威复核。
- 增加统一固定语义 Design Token，收敛 React/Ant Design 与 legacy 的按钮、状态、
  表格、卡片、表单、菜单和反馈组件；删除自有渐变、状态圆点和彩色 Tag 描边。
- React 完成存储、媒体、Bridge/VLAN、任务、审计、设置、节点移除、串口、VNC 与
  Cytoscape 网络拓扑迁移；VM 生命周期和控制台统一放入详情页，复杂配置进入独立
  `/manage/*` 兼容页。
- 收敛重复 Hover Token 与拓扑组件硬编码颜色，统一按钮 Disabled/Focus、网络和
  Snapshot 中文状态；noVNC/xterm 通过动态加载避免普通详情页承担控制台开销。
- 增加状态优先运维工作台：紧凑运行摘要、资源指标、全宽横向子系统状态和渐进式操作区。
- 增加安全格式化 XML/Diff 视图：默认折叠、缩进、行号、语法着色、复制和受控滚动。
- 增加 24 小时 VM 指标历史、节点负载/内存/运行时间采样、有界保留和页面降级展示。
- 增加 Watchdog、vsock、CPU cache/maxphysaddr 的结构化 XML Diff、确认、应用和回滚。
- 增加仅关机 VM 的 PCI/USB Host Device 直通，执行前复核 IOMMU、`vfio-pci`、
  设备身份、占用状态和资源锁。
- 增加配置授权根内的 virtiofs/9p 共享目录写入，默认空授权并执行 `realpath` 重验。
- 增加 Cloud Image IPv6-only 与 IPv4/IPv6 双栈 NoCloud 网络配置和安全校验。
- 建立项目级 Agent 开发规则。
- 增加关机完整克隆：新 UUID/MAC、qcow2/raw/NVRAM 双 SSH 流式复制、SHA-256、
  无覆盖发布、持久化恢复、XML Diff、跨节点网络预检和 revision 0017。
- 建立产品、架构、安全、测试与路线图文档基线。
- 固化多节点复合资源身份、SSH/libvirt 职责边界和任务 lease 模型。
- 固化 XML 未知元素保留、媒体凭据、网络回滚和节点零残留要求。
- 增加 Python/FastAPI 项目骨架、类型化配置和健康检查。
- 增加 SQLite WAL/foreign keys/busy timeout 与 Alembic 启动迁移。
- 增加 Tini、单 worker、非 root 的单容器部署骨架。
- 增加单管理员初始化、登录、退出、账户设置和登录历史。
- 增加 Argon2 密码、opaque Session、CSRF、登录限速和 Host Header 防护。
- 增加浅色响应式认证/设置页面与全局等宽、密度偏好。
- 增加 AES-256-GCM 凭据 envelope、资源绑定 AAD 和版本化 keyring。
- 增加 SSH Host Key 发现、指纹、原子信任文件和变化阻断。
- 增加 typed RemoteExecutor、严格 OpenSSH argv、有界输出、超时、取消和审计。
- 增加 SQLite Task/TaskStep、原子 claim、lease、心跳、检查点和重启识别。
- 增加有限任务协调器、幂等提交、协作取消和基础任务中心。
- 增加本地构建的 Tabler/Tabler Icons、统一导航和响应式页面骨架。
- 增加安全 libvirt XML 解析、版本化 C14N2 hash、Diff 和 CPU topology 局部修改。
- 增加 `nexora-ops` 初始化、一致备份、校验恢复与模块化运维文档。
- 增加 Host、加密凭据、SSH 指纹、能力和远端命令审计持久化模型。
- 增加 Host Key 扫描/确认两阶段节点接入，变化或过期确认会阻断连接。
- 增加 AsyncSSH 密码及内存私钥后端、严格 known_hosts 和真实协议测试。
- 增加 19 步只读节点能力探测、持久化任务进度和节点接入页面。
- 增加 generation 化 ResourceIndex、原始 XML 文档缓存和带外 hash 变化状态。
- 增加已有 VM/快照、Pool/Volume、libvirt Network、宿主接口及 PCI/USB 发现。
- 增加节点资源发现摘要、已有 VM 列表和受 CSRF 保护的手动重新扫描入口。
- 增加通用 ResourceWriteGuard，阻断 stale、missing、conflict 和带外变化写入。
- 增加限时节点移除预览、名称确认、持久化三步任务和不可级联 tombstone。
- 增加严格远端临时实体 allowlist、执行前重验和业务资源零删除验证。
- 增加节点作用域虚拟机列表、详情、Persistent XML 与生命周期操作页面。
- 增加 Domain UUID 资源租约锁、生命周期状态矩阵、并发阻断和写后权威验证。
- 增加结构化 CPU topology 表单、远端 Schema 校验、XML Diff 和限时确认计划。
- 增加 CPU 持久化 XML 异步应用、写后 hash 验证和失败自动恢复原始 XML。
- 增加 current/max memory、HugePages、locked、source、access、allocation 和 discard 表单。
- 增加内存 XML 未知项保留、类型绑定确认计划和 CPU/内存/生命周期粗粒度互斥。
- 增加 ISO/qcow2/raw generation 索引、SHA-256、qemu-img 元数据和缺失状态。
- 增加 `/library` 根限制、symlink 拒绝、文件身份复核和外部 backing 路径脱敏。
- 增加三步持久化媒体扫描任务、媒体库页面和本地 Tabler media 导航。
- 增加 digest-only MediaCredential、最长 30 天租约、一次性显示和即时撤销。
- 增加 ISO HEAD/GET/单 Range、206/416、ETag、If-Range 与有界流式读取。
- 增加 credential ID URL、Bearer header 和 device/inode/size/mtime 文件版本校验。
- 增加权威 Pool 刷新、资源锁续租和 AsyncSSH 流式平台镜像复制。
- 增加任务专属 partial、大小/SHA-256 校验、hard-link 无覆盖发布和幂等恢复。
- 增加中断任务显式恢复入口、CSRF 防护、重试上限和步骤尝试计数保留。
- 增加 Rocky 9.7 嵌套 KVM opt-in 集成测试与专用环境文档。
- 增加 dir/NFS netfs Pool 的 XML Diff、限时确认和持久化任务。
- 增加 Pool define/build、生命周期、autostart、资源锁和权威状态验证。
- 增加只 undefine 且保留数据的删除流程，以及 VM 磁盘引用阻断。
- 增加 NFS mount option 白名单和稳定 Pool 配置 hash，忽略易变容量统计。
- 增加 Rocky 回环 NFSv3 Pool 全生命周期 opt-in 集成测试。
- 增加 revision 0012 Storage Volume 持久化预览、确认和任务状态。
- 增加 qcow2/raw 无覆盖创建、只扩容、显式删除和 Pool/Volume 双锁。
- 增加 Domain 权威引用扫描，阻断运行中 VM 扩容及任意 VM 引用删除。
- 修正 Volume 动态 allocation、physical、timestamps 导致的带外变更误报。
- 增加 dir 与 NFS netfs qcow2 创建、扩容、删除和零残留真实集成测试。
- 增加已有 VM Disk 展示、同节点 managed Volume 挂载和设备卸载。
- 增加 Disk Diff/确认计划、VM/Volume 基线重验、资源锁和异步写后验证。
- 增加 libvirt 新 Disk PCI address 规范化验证，拒绝无关 Domain XML 变化。
- 增加运行中 VM persistent Disk 挂载/卸载及 backing 保留真实集成测试。
- 增加已有 persistent CD-ROM 展示和同节点 managed raw ISO 换盘。
- 增加 CD-ROM 弹出、限时 Diff 确认、VM/ISO 双锁和 config-only 任务。
- 增加真实运行中 VM CD-ROM 弹出/挂载、原 XML 恢复和零残留集成测试。
- 增加源 IP、VM、媒体 SHA-256 绑定的平台 HTTP ISO 与可撤销 Range 访问。
- 增加 `/var/tmp/nexora-media-{sha256}.iso` 远端缓存回退、任务 partial、校验、
  无覆盖发布、共享引用保护及零引用清理。
- 增加 Rocky QEMU HTTP whitelist 能力边界与缓存 QEMU 启动真实集成测试。
- 将后续视觉方向调整为现代明亮、鲜活彩色强调，并保留 WCAG AA 与克制内容面。
- 增加 VM 详情页已有 Snapshot 列表、创建时间、状态、内存/磁盘模式及安全 XML 展示。
- 增加 Rocky 带外 internal Snapshot 自动发现、无需导入和测试资源零残留验证。
- 增加 revision 0013 Snapshot 独立持久化预览、确认、任务和结果状态。
- 增加关机 qcow2 VM 原子 internal Snapshot 创建、双锁、带外阻断与权威验证。
- 增加真实 Rocky 持久化任务快照创建和 VM/磁盘零残留验证。
- 增加 Snapshot parent/current 权威发现和 internal leaf 安全删除。
- 删除前后复核完整拓扑、Snapshot hash 与 VM XML；拒绝 children/metadata/force。
- 增加配置等价 current internal leaf 的磁盘恢复和 VM 名称二次确认。
- 增加真实 Rocky `qemu-io` 字节模式 A/B/A 数据回退验证。
- 增加 VM `domstats` CPU/内存/磁盘/网络实时采样与 HTMX 5 秒局部刷新。
- 指标差分使用单 worker 有界内存缓存，不向 SQLite 写入高频时序数据。
- 增加 revision 0014 VM 创建确认计划、`vm.create` 三步任务和 verify-only 恢复。
- 增加从同节点未引用 managed qcow2/raw Volume 创建 BIOS persistent VM。
- 增加 domcapabilities 架构探测、结构化 Domain XML、schema 校验和完整创建 Diff。
- 增加 Volume→VM UUID 双锁、带外复核、写后发现验证和失败零磁盘操作。
- 增加创建页候选引用过滤、1280/375px QA 与真实 Rocky 定义/启动/清理测试。
- 增加创建时可选同节点 Linux Bridge 或 active managed libvirt Network。
- 增加网络复合身份/hash 权威刷新、跨节点阻断与结构化 VirtIO interface XML。
- 增加 libvirt 自动 MAC 写后验证和真实 `default` Network 不变性测试。
- 增加 VM 创建时同节点 managed raw ISO 选择与 readonly SATA CD-ROM。
- 增加 ISO Volume/Pool/hash 权威复核、双 Volume 有序锁和 CD-ROM 写后验证。
- 增加真实 Rocky 系统盘+Network+ISO 定义、启动与三资源精确清理。
- 增加 revision 0015 平台镜像 VM 独立确认计划和可恢复五步任务。
- 增加 qcow2/raw 完整复制、SHA-256、Pool refresh、Volume 发现后定义 VM。
- 增加平台镜像外部 backing 拒绝、目标文件/VM 双锁及碰撞无覆盖恢复。
- 增加平台镜像创建页、375px QA 和真实 Rocky 复制/启动/零残留测试。
- 增加 Cloud Image 的 NoCloud hostname、用户、SSH 公钥和 DHCP 初始化。
- 增加计划 MAC、readonly seed CD-ROM、受控远端 ISO 生成和内容哈希恢复验证。
- 增加真实 Rocky system+seed 双 Volume、VM 启动、恢复复核与零残留测试。
- 增加 QEMU Guest Agent channel、连通状态、Hostname 与全局 IP 只读采集。
- 增加 15 秒 Guest Agent HTMX 卡片、真实 Rocky unavailable 验证和局部失败降级。
- 增加本地构建的 htmx 2.0.4 静态资源，修复性能与 Guest Agent 卡片未触发请求。
- 增加 revision 0016 一次性 ConsoleSession、摘要 Token、Session/Origin/用途绑定。
- 增加本地 xterm.js 串口页与 FastAPI WebSocket 到 AsyncSSH PTY 的双向桥接。
- 增加真实 Rocky `virsh console --safe` 握手、浏览器关闭和零进程残留验证。
- 增加 noVNC 1.7.0 页面、回环 VNC endpoint 校验和 AsyncSSH local forward。
- 增加 Nexora 单次 websockify worker、二进制帧限制、进程组与 shutdown 清理。
- 增加真实 Rocky RFB banner、浏览器 canvas 连接及 worker/Tunnel 零残留验证。
- 增加 Cloud Image SHA-512 crypt 密码、结构化静态 IPv4 和 grow-only 磁盘扩容。
- 增加 revision 0018 扩容后 SHA-256 恢复门禁、远端容量复核和路径穿越测试。
- 扩大 Tabler checkbox 点击区域，桌面与 375px 所有可见交互目标达到 44px。
- 增加 host-scoped 只读网络拓扑模型，关联物理口、VLAN、Bridge、tap/vnet 与 VM。
- 增加管理链路、默认路由、Carrier、link state 与 MTU 不一致文字标记。
- 将 `/networks` 占位页替换为节点选择、摘要、节点表和关系表的可访问回退页面。
- 将 `/audit` 占位页替换为有界分页、节点/结果筛选和脱敏输出摘要页面。
- 审计视图限制每页 50 条、单字段 2 KiB，并对命令及输出执行模板转义。
- 落实现代明亮鲜活 Design Token，统一导航、卡片、按钮、表单、表格、Badge、
  认证页、焦点与 reduced-motion，并完成 375/768/1024/1440px Browser QA。
- 宿主接口发现改用只读 `ip -d -j link show`，正确保留 Bridge、VLAN 与 vnet/tap
  类型，避免将 libvirt tap 接口误标为物理接口。
- 增加 opt-in 真实密码 SSH 与普通用户免密 sudo 测试，覆盖严格 Host Key、
  `RemoteExecutor` 审计脱敏和测试用户/sudoers/进程零残留。
- 增加 opt-in 加密 Ed25519 私钥口令测试，覆盖内存私钥、strict known_hosts、
  审计脱敏和测试用户/Home/进程零残留。
- 在真实 Rocky 临时切换五个 modular libvirt daemon，验证接入、VM/Pool/Network/
  PCI/USB 发现、镜像复制、节点移除以及恢复传统 libvirtd 后业务资源保留。
- 将 VM 启动、关机、重启、暂停、恢复、保存状态、强制操作及一次性控制台入口迁移到
  React 详情页；复杂配置继续通过独立“配置”入口进入现有管理页。
- 增加 Session-only VM 生命周期 JSON API，由服务端读取当前 generation/hash，危险
  操作要求虚拟机名称确认，并继续复用持久化任务队列。
- 将存储池/卷、平台媒体索引与扫描、任务列表/详情/取消/恢复迁移到 React + Ant
  Design，统一语义按钮、状态标签、表格和响应式布局。
- 增加可配置端点的发行版 opt-in 集成测试，并在 Debian 13 nested KVM 验证普通
  用户 sudo、能力探测、宿主接口及平台外已有 VM 自动发现。
