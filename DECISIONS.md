# Architecture Decision Records

## ADR-001：FastAPI 服务端 Web

- 日期：2026-07-28
- 决定：FastAPI + Jinja2 + HTMX，少量局部 JavaScript。
- 原因：保持单体、轻量和渐进增强，避免 SPA 与常驻 Node 服务。

## ADR-002：Tabler UI

- 日期：2026-07-28
- 状态：由 ADR-034 取代。
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

## ADR-014：AsyncSSH 作为认证执行主后端

- 日期：2026-07-28
- 决定：密码和内存私钥认证统一使用 AsyncSSH，并强制独立 known_hosts。
- 原因：避免私钥落盘，同时获得流式限额、超时和通道取消能力。
- 约束：禁用环境 SSH config、agent 和 ProxyCommand；业务仍只调用 RemoteExecutor。
- 影响：OpenSSH 只承担 Host Key 扫描、客户端工具和受控兼容回退。

## ADR-015：按资源类型提交发现 generation

- 日期：2026-07-28
- 决定：每类资源使用独立 scan generation，成功后原子更新索引和缺失状态。
- 原因：单类扫描失败时不得把上次可见资源误标为 missing。
- 约束：远端 XML/JSON 是权威快照；本地标签和备注在重新扫描时保留。
- 影响：persistent hash 未经平台操作发生变化时保持 changed_out_of_band。

## ADR-016：节点移除使用持久化确认计划

- 日期：2026-07-28
- 决定：移除前保存限时预览，确认后由持久化任务执行并生成 tombstone。
- 原因：远端临时实体必须在确认和执行时完全一致，防止范围漂移。
- 约束：只允许固定临时根下的 `nexora-*` 和严格 transient unit；业务删除为零。
- 影响：本地凭据、Host Key 和缓存级联删除，脱敏审计墓碑不级联删除。

## ADR-017：虚拟机写操作使用权威刷新与资源锁

- 日期：2026-07-28
- 决定：生命周期写操作以节点 ID 与 Domain UUID 定位，先加数据库租约锁再刷新远端状态。
- 原因：同名 Domain 不能作为身份；页面缓存、并发任务和带外修改均可能使写入前提失效。
- 约束：写前经过 ResourceWriteGuard，命令参数类型化，写后轮询权威状态并刷新索引。
- 影响：操作超时或最终状态不符时任务失败，不得仅凭 `virsh` 退出码报告成功。

## ADR-018：结构化 XML 变更使用持久化确认计划

- 日期：2026-07-28
- 决定：CPU 等结构化变更保存原始/目标 XML、Diff、双端 hash 与限时 token。
- 原因：确认内容必须与最终应用内容一致，容器退出后仍能识别操作意图和恢复边界。
- 约束：预览先做远端 Schema 校验；应用仅接受原基线，结果不符时恢复原始 XML。
- 影响：运行中 VM 首期仅更新持久化 XML并明确提示重启，不隐式执行热修改。

## ADR-019：内存配置首期仅修改持久化 XML

- 日期：2026-07-28
- 决定：current/max memory 与 memoryBacking 使用局部变换，运行中 VM 不隐式热插拔。
- 原因：HugePages、locked、memfd 和 NUMA 约束依赖宿主能力，热应用边界差异较大。
- 约束：保留未知属性、子项和 HugePages page；Schema 校验失败时不得创建任务。
- 影响：页面明确标记重启要求，后续按 domcapabilities 增加独立热修改判断。

## ADR-020：媒体扫描使用只读文件身份验证

- 日期：2026-07-28
- 决定：仅扫描 library 根内常规文件，拒绝 symlink，并在哈希/检查前后核对文件身份。
- 原因：路径规范化本身不能消除扫描过程中的 symlink 交换与文件替换竞态。
- 约束：索引只保存相对路径；外部 backing 路径脱敏；失败扫描不得提交 missing 状态。
- 影响：媒体原文件可只读挂载，扫描和删除索引均不需要原文件写权限。

## ADR-021：媒体秘密不进入 URL

- 日期：2026-07-28
- 决定：内容 URL 只包含 opaque credential ID，秘密通过 Authorization Bearer 传递。
- 原因：URL path/query 通常进入 Uvicorn、反向代理、浏览器历史和监控日志。
- 约束：数据库只保存 token digest；凭据绑定媒体 SHA-256，可撤销且最长 30 天。
- 影响：浏览器继续使用 Bearer；QEMU URL 仅含非秘密 credential ID，并同时绑定节点
  源 IP、VM、媒体 ID 和 SHA-256。仅凭 URL 无法从其他来源读取内容。
- 约束：不得使用 query token 或写入 cookie/Bearer；节点地址必须是可验证 IP。

## ADR-022：镜像复制使用任务 partial 与无覆盖发布

- 日期：2026-07-28
- 决定：写前权威刷新并锁定 Pool，流式写入任务专属 partial，校验后以 hard link 发布。
- 原因：普通 rename/mv 可能在竞态下覆盖同名文件，直接写最终路径无法安全识别中断。
- 约束：partial 含 Task ID；只清理本任务实体；最终文件存在时必须验证大小和 SHA-256。
- 恢复：启动只标记 interrupted，管理员显式重试后验证远端状态，不自动重放远端写入。
- 影响：同一 Pool 首期串行写入；任务协调器心跳同时续租资源锁。

## ADR-023：Storage Pool 写入使用持久化定义计划

- 日期：2026-07-28
- 决定：dir/netfs Pool 创建和 undefine 使用 UUID 绑定的限时确认计划、Diff 和异步任务。
- 原因：Pool 名称、Target、NFS Export 与 VM 磁盘引用均可能在页面打开后发生变化。
- 约束：写前重新扫描 Pool 与 Domain；仅支持安全 mount option；不修改 `/etc/fstab`。
- 删除：只执行 stop/undefine，禁止删除 Target、Volume、Export 或业务文件。
- 恢复：按计划 UUID 识别本任务定义；状态不一致时冲突，不盲目重放。
- Hash：Pool 配置 hash 排除 capacity/allocation/available 等易变统计字段。
- 影响：被 VM file path 或 volume pool 引用的 Pool 必须先解除引用才能 undefine。

## ADR-024：平台 ISO 使用 HTTP 优先与远端缓存回退

- 日期：2026-07-29
- 决定：节点支持时使用源 IP 绑定的 HTTP Range；否则复制到
  `/var/tmp/nexora-media-{sha256}.iso` 后挂载。
- 原因：部分发行版 QEMU 即使安装 curl block driver，仍会因编译时 block driver
  whitelist 拒绝 HTTP；libvirt define 成功不能证明 QEMU 启动时可读取。
- 约束：两条路径首期只允许已关闭 VM；缓存以 task partial 写入，校验大小和
  SHA-256 后无覆盖发布，并以节点、路径资源锁串行。
- 探测：从 `virsh domcapabilities` 读取受限 emulator 路径，以 machine-none 和
  QMP quit 对同一 system QEMU 执行临时 HTTP blockdev 探测；失败即撤销凭据。
- 清理：弹出后重新扫描全部 Domain，仅在零引用时删除精确缓存文件；节点移除仅清理
  Nexora 命名空间，绝不清理业务 ISO。
- 影响：UI 将缓存回退作为推荐路径，HTTP 路径明确标注需要节点能力支持。

## ADR-025：Snapshot 写入使用独立持久化确认计划

- 日期：2026-07-29
- 决定：Snapshot 不复用 Domain XML 计划；revision 0013 保存操作、VM 基线、
  快照身份、Diff、限时确认摘要和最终状态。
- 首期边界：仅关机持久化 VM；全部可写磁盘必须为绝对路径 file/qcow2；使用
  `virsh snapshot-create-as --atomic` 创建不含内存的内部快照。
- 并发：任务同时持有 host + VM UUID 与 host + Domain UUID/Snapshot name 锁。
- 验证：执行前刷新 VM/快照并阻断同名和带外变化；执行后重新发现 Snapshot XML，
  要求 memory=no、磁盘模式 internal/no 且 VM persistent XML hash 不变。
- 恢复：策略为 verify_only；创建结果不明确时禁止自动删除或盲目重放。
- 删除：仅允许 memory=no、internal、无子节点 leaf；禁止 children、metadata 和
  自动重试，并验证其他 Snapshot hash 与 VM XML 未变化。
- 恢复：仅允许 state=shutoff、memory=no、配置 hash 等价的 current internal
  leaf；禁止 force/running/paused/reset-nvram，并要求再次输入 VM 名称。
- 影响：外部快照、运行中快照、非 leaf 删除和历史分支恢复保持只读。

## ADR-026：VM 导入创建绑定 managed Volume

- 日期：2026-07-29
- 决定：首个 VM 创建切片仅从同节点未引用的 managed qcow2/raw Volume 定义
  persistent VM；不接受页面路径，不复制、覆盖、扩容或删除磁盘。
- XML：通过 lxml 结构化生成 BIOS Domain，架构来自 `virsh domcapabilities`；
  远端 schema 校验后展示完整创建 Diff，默认关机且不添加网卡。
- 计划：revision 0014 保存 Volume 基线、生成 UUID、结构化输入、XML、Diff 和
  确认摘要；`vm.create` 三步任务持有 Volume→VM UUID 双锁。
- 恢复：verify_only；仅当中断后发现的 VM 名称、UUID、内存、vCPU、磁盘与计划
  完整匹配时成功，否则冲突。失败不自动 undefine，也不操作 Volume。
- 网络：可选同节点 Linux Bridge 或 active/persistent managed libvirt Network；
  仅生成 VirtIO 引用，不修改网络资源，执行前复核 ifindex/UUID、名称和 hash。
- 本地 ISO：可选同节点 active dir/netfs 中 managed raw `.iso`，生成 readonly SATA
  CD-ROM；系统盘与 ISO 按 native ID 排序加锁，失败不弹出、修改或删除 ISO。
- 影响：平台 ISO、Cloud Image、UEFI/TPM 和复制镜像创建在后续切片扩展。

## ADR-027：平台镜像创建采用复制后定义的可恢复编排

- 日期：2026-07-29
- 决定：平台 qcow2/raw 必须完整复制到同节点 managed dir/netfs Pool，校验后刷新
  Volume 索引，再定义 persistent VM；禁止通过 HTTP 运行系统盘或使用平台 backing。
- 计划：revision 0015 使用独立确认计划保存 Media SHA、Pool 基线、目标文件、
  Domain XML 和 Diff；不把尚未存在的目标文件伪装成 ResourceIndex。
- 恢复：`vm.create_from_media` 每次从远端状态判定；同 SHA 最终文件可复用，
  task partial 可精确清理，完整匹配的既有 VM 可确认成功，其他碰撞均阻断。
- 失败：只自动删除任务 partial；已校验发布的最终文件保留以支持恢复或人工处置。
- 影响：首期不 convert、扩容、cloud-init、UEFI 或自动启动，后续分别扩展。

## ADR-028：Cloud Image 首期使用远端 NoCloud seed

- 日期：2026-07-29
- 决定：在平台镜像复制任务内生成 readonly NoCloud seed，首期支持 hostname、
  普通用户、SSH 公钥和按计划 MAC 匹配的 DHCP，不保存或支持明文密码。
- 工具：只探测远端已有 genisoimage/mkisofs 与 xorriso/isoinfo，不自动安装。
- 安全：固定 bash 脚本、平台派生路径、0700 临时目录、敏感环境、task partial 和
  hard-link 无覆盖发布；页面不能提交 seed 路径或脚本。
- 恢复：提取 seed 内三份文件并比较计划内容 SHA-256；不匹配即碰撞阻断。
- 影响：密码需 AEAD 计划，静态 IP 与扩容需独立结构化步骤后再开放。

## ADR-029：Guest Agent 采用只读按需采集

- 日期：2026-07-29
- 决定：从 persistent/live Domain XML 识别标准 channel，仅对运行中 VM 使用固定
  `guest-ping`、`guest-get-host-name` 和 `guest-network-get-interfaces`。
- 边界：不进入客户机安装 Agent，不执行任意命令，不持久化原始响应；过滤回环、
  link-local 和 unspecified 地址，并限制接口、地址与输出规模。
- 页面：使用本地构建的 htmx 2.0.4 每 15 秒刷新局部卡片；运行时不依赖 CDN 或
  Node.js。未配置、停止和不可用均作为正常可解释状态展示。
- 影响：首期不展示用户、进程、文件系统或任意 guest-exec 数据；历史只保留未来
  明确定义的低频聚合字段。

## ADR-030：控制台使用一次性会话与用途分离传输

- 日期：2026-07-29
- 决定：revision 0016 保存 token 摘要及管理员 Session、host、VM、用途绑定；
  pending 60 秒且只能原子 claim 一次，活动会话空闲 5 分钟、最长 60 分钟。
- 串口：FastAPI WebSocket 直接桥接严格 AsyncSSH PTY 与固定
  `virsh console --safe`，不为串口启动额外代理进程。
- Web：Token 放在非回显的 WebSocket subprotocol 项，URL/query/cookie 不含 Token；
  服务端只选择 `nexora.console`，同时验证 HttpOnly Session 与严格 Origin。
- 恢复：启动时 active 标记 interrupted；浏览器关闭、超时和 shutdown 关闭 SSH。
  host 删除通过外键级联本地记录，不操作远端 VM 或 XML。
- 影响：VNC 复用同一会话表，但采用独立 kind、SSH Tunnel 与 websockify transport。

## ADR-031：VNC 使用受控单次 websockify worker

- 日期：2026-07-29
- 决定：noVNC 1.7.0 通过 `binary` subprotocol 连接 FastAPI；后端经 AsyncSSH
  local forward 到远端回环 VNC，并为每个会话启动 Nexora 自有单次 worker。
- 原因：PyPI websockify 0.13.0 强制引入 Redis 客户端及 numpy/requests 等无关
  依赖，违反“不得依赖 Redis”硬门禁，已从 pyproject 和 lock 中完整移除。
- 进程：worker 只绑定容器 127.0.0.1 动态端口，固定目标为 Tunnel 动态端口；
  单连接、二进制帧、64 KiB 上限、5 分钟空闲，使用独立进程组并由主进程/Tini 回收。
- 安全：仅接受无密码的单一 VNC graphics 与 loopback domdisplay；不展示 XML 中的
  listen/password/socket，不支持 SPICE 自动转换或远端监听修改。

## ADR-032：完整克隆采用双 SSH 流式复制与无覆盖发布

- 日期：2026-07-29
- 决定：revision 0017 保存源 VM/目标 Pool 基线、文件 manifest、新 UUID/MAC、
  目标 XML、Diff 和确认摘要；`vm.clone` 按文件持久化进度与 checkpoint。
- 传输：源、目标分别使用严格 Host Key 与内存凭据的 AsyncSSH 会话，固定 reader
  stdout 以 1 MiB chunk 流向固定 writer stdin；容器本地不保存虚拟磁盘。
- 安全：只接受关机 persistent VM 的非共享 file qcow2/raw，拒绝 backing chain、
  managed-save、Host Device 和目标网络缺失；路径只来自 XML 与 Pool target。
- 发布：任务 partial 完成 size/SHA-256 后 hard-link 无覆盖发布；恢复可复用同 hash
  最终文件，失败只清理本任务 partial，永不修改或删除源 VM/磁盘。
- 兼容：同节点 Rocky 已实测启动；跨节点实现架构及 Bridge/libvirt Network 预检，
  挂载本地文件 CD-ROM 时阻断，双节点实测仍是兼容矩阵待办。

## ADR-033：Cloud Image 密码与扩容采用不可逆恢复凭据

- 日期：2026-07-29
- 决定：浏览器提交的客户机密码在请求线程内立即转换为 SHA-512 crypt；
  NoCloud、计划与任务只保存 shadow-compatible hash，不保存可解密明文。
- 网络：静态 IPv4 只接受结构化 CIDR、同子网 gateway 和最多三个 IP DNS；
  不接受任意 YAML，并与计划 MAC 的 network-config v2 绑定。
- 扩容：完整复制和源 SHA-256 校验后才执行固定 `qemu-img resize` grow；
  revision 0018 持久化扩容后 SHA-256。
- 恢复：目标容量和扩容后 SHA-256 必须同时匹配才可复用；缺失 hash、容量异常或
  内容变化均转为冲突，不盲目复制、覆盖、缩容或重新扩容。

## ADR-034：分阶段迁移到 React 与 Ant Design

- 日期：2026-07-31
- 决定：前端最终使用 React、TypeScript、Vite、Ant Design 6 和 React Router；
  FastAPI 提供同源内部 Session API 与 React HTML 外壳。
- 视觉：紧凑顶部导航、标准舒适密度、浅色主题和浅亮无边框状态 Tag。
- 运行：Node.js 只用于镜像构建，运行时继续为单容器、单 Uvicorn worker。
- 迁移：按基础平台、核心只读、资源详情、创建变更、运维页面和收敛清理推进；
  同一 URL 只由一种前端负责，阶段间必须可独立部署和回滚。
- 安全：Session、CSRF、危险操作、Diff、确认 Token、任务与审计语义保持不变；
  React 不新增公共 API、Token 或敏感浏览器持久化。
- 路由：2026-08-01 复核 React Router `7.18.2` 仍有 2 个 high 漏洞，P8-002 不引入；
  核心三个 URL 暂用同源 History API，漏洞修复后再切换，不降低 URL 隔离要求。
- 收敛：2026-08-01 主工作台、资源变更与运维页面完成 React 接管；根据产品确认，
  初始化/登录和复杂 VM 配置继续作为独立 Jinja `/manage/*` 兼容岛，不在同一 URL
  混用前端。其 HTMX/Tabler 构建资产仅为兼容岛保留，后续迁移必须保持全部安全预检。

## ADR-035：不实现节点级只读门禁，kvm1 通过人工流程保护

- 日期：2026-08-05
- 背景：kvm1 为生产机器，含 PCIe 设备，需避免误操作；曾计划实现节点级只读标记。
- 决定：不实现系统级只读能力。曾实现 `Host.read_only` 字段、迁移
  `20260803_0023`、`ensure_host_writable` 写路由守卫与 `HostSummary.read_only`
  暴露，经确认后全部回滚，未落地任何代码或数据库改动，迁移链保持
  head `20260803_0022`。
- 理由：只读门禁增加模型、迁移、路由守卫与前端禁用逻辑的系统复杂度，而需求本质
  是对单台生产节点的操作纪律；人工确认与运维流程已覆盖该风险。
- 约束：对 kvm1 的任何写操作（生命周期、配置、存储、网络、直通、删除等）须经用户
  显式确认后执行；日常读操作不受影响。
- 影响：无 schema 变更、无迁移、无 API 契约变化、无前端变化；PCIe 直通能力判定
  （P8-011）与关机直通操作（P7-003）维持现状。

## ADR-036：管理员密码最低长度调整为 8 位

- 日期：2026-09-16
- 决定：管理员初始化和账户改密的最低密码长度统一调整为 8 个字符，最大长度保持
  1,024 个字符；后端校验、React 初始化/账户页面和测试保持一致。
- 原因：满足已确认的当前部署使用需求，同时不改变当前密码验证、Argon2 哈希、CSRF、
  Session 撤销和登录审计机制。
- 风险：相较原 12 位门槛降低密码安全基线；不新增常见弱口令或复杂度黑名单，生产
  管理员仍应使用更长且不可预测的密码。
- 影响：无数据库迁移和哈希格式变化；已有密码不自动改变，改密仍须验证当前密码。
