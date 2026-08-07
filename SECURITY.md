# Nexora 安全基线与威胁模型

## 信任边界

- 浏览器与 Nexora Web/Session 边界。
- Nexora 容器与 `/data`、`/library` 边界。
- Nexora 与不完全可信远端节点之间的 SSH 边界。
- QEMU 通过媒体 URL 访问 Nexora 的媒体边界。
- 管理员输入与命令、XML、路径、URI 的解释边界。

远端节点可能失陷或返回恶意输出；不得信任命令输出、XML、文件名或设备元数据。

## 主要威胁与控制

| 威胁 | 强制控制 |
|---|---|
| SSH 中间人 | 严格 Host Key、显式首次确认、变化阻断 |
| 凭据泄漏 | AEAD、字段脱敏、密钥外置、最小日志 |
| 命令/参数注入 | typed adapter、统一 quoting、禁 shell fragment |
| XML XXE/炸弹 | 禁 DTD/实体/网络/XInclude，限制尺寸和深度 |
| 路径/符号链接逃逸 | allowlist 根、realpath、原子创建、归属验证 |
| CSRF/Session 劫持 | CSRF、HttpOnly、Secure、SameSite、Session 轮换 |
| XSS | 默认转义、CSP、Diff/日志转义、禁止不可信 HTML |
| WebSocket 劫持 | Origin、Session 和一次性 token 绑定 |
| SSRF/URI 注入 | scheme allowlist、地址验证、禁止 SSH 配置注入 |
| 重复危险操作 | 幂等键、资源锁、外部状态验证 |
| 带外覆盖 | generation/hash、三方 Diff、冲突阻断 |
| 网络失联 | 独立回滚任务、确认期限、无回滚则拒绝 |
| 恶意远端输出 | 输出限额、超时、安全解析、终端转义处理 |
| 审计删除 | 审计不可级联删除、保留资源 tombstone |

## Web 安全

- 所有状态变更包含 CSRF；初始化和登录同样受保护。
- 登录成功和权限变化后轮换 Session ID；改密后撤销旧 Session。
- 响应使用 CSP、`frame-ancestors`、nosniff 和 Referrer-Policy。
- 校验 Host Header；生产明确受信代理和 HTTPS 终止边界。
- Token、密码、私钥、口令、Cookie 和完整 URI query 不进入日志。
- React 内部只读 API 必须认证、`no-store`、分页限界并最小化字段；页面加载只读
  SQLite 权威索引，不得隐式触发 SSH 或 libvirt 全量扫描。列表 API 不返回 XML；
- 节点硬件只采集 CPU、内存、NUMA、厂商、产品型号和网卡 MAC；禁止采集主机或
  磁盘序列号、DMI UUID、asset tag，原始 `lscpu`/DMI 输出不得直接返回页面。
  详情 API 仅返回当前资源绑定的有界缓存 XML，并在服务端经禁用 DTD、外部实体、
  网络和 XInclude 的安全解析入口验证后格式化。Guest Agent 状态读取仍使用固定命令。

## 凭据

- 使用 AES-256-GCM 或 ChaCha20-Poly1305 等 AEAD。
- 每条记录使用随机 nonce，AAD 绑定 host、credential ID 和 schema version。
- `NEXORA_SECRET_KEY` 与 `NEXORA_CREDENTIAL_KEY` 独立。
- 密文保存 key version，支持分批重加密和可恢复轮换。
- 缺少或错误密钥时 fail closed；禁止以空值或临时密钥启动。
- 备份不包含环境主密钥，恢复必须显式提供原密钥。

## 权限与供应链

容器非 root、最小 capabilities、无 privileged、无宿主 socket。远端使用最小 sudo
范围；平台不写 sudoers。依赖锁定，发布生成 SBOM、许可证清单和漏洞扫描结果。

## 审计

认证、Host Key、凭据轮换、危险预检/确认、远端命令摘要、任务状态、资源冲突、
网络回滚和节点移除均写审计。审计只保存脱敏信息，并设置独立保留和备份策略。

节点移除确认 token 只保存摘要并设短期有效期；确认绑定 plan、host scope 和节点名称。
临时实体清单在执行前重新读取，集合变化即阻断。移除 tombstone 不保存 SSH 密码、
私钥、Host Key 原文或 Session 信息。

Storage Pool 创建和 undefine 使用 UUID 绑定的限时确认计划。Target/Export 必须是
规范绝对路径，NFS mount option 采用白名单；写前重新扫描 Pool 与 Domain。存在
VM file path 或 volume pool 引用时拒绝 undefine。删除操作仅移除 libvirt 定义，
不得删除 Target、Volume、NFS Export 或业务文件。

Storage Volume 写入绑定 host、Pool UUID、Volume Key 和双资源锁。扩容只允许增大，
运行中 VM 引用时拒绝；删除对任何 VM 引用均拒绝，且不自动重试。Volume 配置 hash
排除 allocation、physical 和 timestamps 等动态统计，但原始 XML 仍完整保存。

VM Disk 挂载只接受同节点已索引的 managed qcow2/raw Volume，不接受页面提交的任意
路径。写前复核 VM/Volume generation/hash、现有引用和双资源锁。写后允许 libvirt
仅为新 Disk 生成 PCI address；移除该新 Disk 后其余权威 XML 必须与原 hash 一致。
卸载只删除设备定义，默认且隐式禁止删除 Volume 或 backing 文件。

CD-ROM 本地换盘只接受同节点 managed dir/netfs Pool 中已索引的 raw `.iso` Volume，
并按 target、bus、expected source 复核已有设备。弹出仅移除 source，挂载不改变
Controller/address，任何操作均不删除 ISO。平台 HTTP ISO 继续受 ADR-021 约束：
不得退化为 query token，媒体秘密不得写入 Domain XML 或持久计划。QEMU 直连 URL
只含非秘密 credential ID，并由服务端同时验证节点源 IP、VM、媒体及 SHA-256。
直连预探测只执行 domcapabilities 返回且位于 `/usr/bin`、`/usr/lib` 或
`/usr/libexec` 的 `qemu-kvm`/`qemu-system-*`，使用参数数组、machine-none 和
QMP quit；探测失败或路径异常即撤销凭据并拒绝直连。

平台 ISO 缓存回退只允许精确的 `/var/tmp/nexora-media-{sha256}.iso` 命名空间。
写入使用任务专属 partial、大小/SHA-256 校验和无覆盖发布；弹出后必须扫描全部
Domain，仅在零引用时删除。路径校验、删除命令和测试清理均不得接受任意页面路径。

Snapshot 创建使用独立限时确认计划，绑定 host、VM UUID、resource generation/hash
和安全 ASCII Snapshot name。首期拒绝运行中、transient、无 writable qcow2 及任何
非 file/qcow2 可写磁盘组合；不接受页面提交的磁盘路径。执行前后均刷新权威状态，
使用 VM/Snapshot 双锁和原子 libvirt 操作。结果不明确时只验证，不自动删除快照或
重放写入，避免破坏磁盘链。
Snapshot 删除进一步要求目标为 memory=no 的 internal leaf，并重新读取 parent/current
拓扑；禁止 children、children-only、metadata 和 force。删除结果不明确时只验证，
不得自动重试、回滚到 Snapshot 或操作相邻磁盘链。
Snapshot 恢复仅允许配置 hash 与当前 persistent Domain 相同的 current internal
leaf，VM 与 Snapshot 均须记录为 shutoff。页面要求 VM 名称二次确认；命令永久禁止
force、running、paused 和 reset-nvram。失败后只验证权威状态，不自动重放恢复。

VM 实时指标仅通过固定 `virsh domstats` 参数读取，限制输出行、字段长度和设备数量。
页面只显示聚合计数，不暴露磁盘路径或未知远端字段。差分缓存有 2,000 项和 15 分钟
上限，只保存计数器与单调时间，不包含凭据且不持久化。

VM 导入创建只接受 ResourceIndex 中同节点、active dir/netfs Pool 的 managed
qcow2/raw Volume。候选页提前排除已引用 Volume，预览和执行仍重新扫描 Storage 与
Domain 并复核 generation/hash、名称、UUID 和引用。页面不得提交路径、emulator、
libvirt URI 或任意 XML；磁盘路径与格式只来自权威索引。任务持有 Volume→VM 双锁，
中断后只验证完整匹配结果，不自动 undefine VM 或删除、覆盖、扩容磁盘。

创建网卡只接受同节点 ResourceIndex 中 kind=bridge 的 Host Interface，或 active、
persistent、managed 的 NAT/isolated libvirt Network。页面只提交 resource ID，
不能提交 Bridge/Network 名称、MAC 或 XML。预览和执行刷新相应权威资源并复核
ifindex/UUID、名称、generation/hash；网卡只引用网络，不执行任何宿主机网络写入。

创建时本地安装 ISO 只接受同节点 active managed dir/netfs Pool 中已索引的 raw
`.iso` Volume。页面只提交 resource ID，不提交路径；权威路径必须绝对且扩展名匹配。
ISO 以 readonly SATA CD-ROM 引用，可安全共享。系统盘与 ISO Volume 锁按 native ID
排序，避免双资源死锁；失败和恢复均不得弹出、修改或删除 ISO。

平台镜像创建只接受可用且无外部 backing chain 的已索引 qcow2/raw MediaItem。
页面只提交 Media、Pool、Network 和 ISO 的资源 ID 及受限目标 basename；目标路径
只能由权威 Pool target 派生。复制沿用任务 partial、大小/SHA-256 和 hard-link
无覆盖发布，随后必须 refresh Pool 并验证新 Volume 无 backing。任务持有目标文件
身份锁与 VM UUID 锁；恢复只接受同 SHA 文件或完整匹配 VM，任何碰撞不得覆盖。

Cloud-init seed 仅由固定文档模型生成，首期不接受明文密码和任意 YAML。hostname、
用户名、SSH 公钥与计划 MAC 均有格式/长度限制；seed 路径由 Pool target 和 VM UUID
派生。远端固定脚本只在 `/var/tmp/nexora-cloudinit-{task_id}` 写入，使用 0700、
trap、task partial 和无覆盖发布，敏感 stdin/env 不进入审计。恢复必须只读提取
user-data、meta-data、network-config 并比较 SHA-256，不得信任同名 ISO。

Cloud Image 密码只在当前 Web 请求内存中存在，立即通过固定本地 `openssl`
SHA-512 crypt 转换；不得进入计划、任务、审计、页面响应或 seed 的明文字段。
静态 IPv4 拒绝 loopback、link-local、multicast、unspecified、跨子网 gateway 和
重复 DNS。扩容只允许已校验完整副本 grow，并持久化扩容后 SHA-256；恢复必须同时
验证 virtual size 与该 SHA，任何歧义状态都不得自动继续。

Guest Agent 读取只允许固定 `virsh qemu-agent-command` 请求，不接受页面提交的
command 或 JSON。只有标准 channel 且 VM 运行时才访问；输出、接口数、每接口地址数
和字段长度均有上限。远端 stderr 与原始 JSON 不进入页面，异常局部降级且不得触发
安装、guest-exec、文件读取或其他客户机写操作。

控制台 token 只保存 SHA-256 摘要并绑定当前管理员 Session hash、host、VM 和用途。
明文只在创建响应和浏览器内存短暂存在，不得进入 URL、query、cookie、日志或审计。
WebSocket 必须验证严格 Origin、HttpOnly Session 和一次性原子 claim，只回显不含
秘密的协议名。串口远端命令固定且使用 canonical UUID；终端输入输出不持久化。

VNC endpoint 只接受 `virsh domdisplay` 返回的回环地址和有界端口，并与 live XML
中的唯一、无密码 VNC graphics 交叉验证。Tunnel 和 worker 仅监听容器回环地址，
动态端口不映射到宿主机；worker 只接收二进制帧并限制大小。不得为了使用第三方
websockify 而引入 Redis 依赖，也不得把 VNC password 复制到页面。

完整克隆只接受页面提交的源 Resource ID、目标 Pool ID 和受限名称；源/目标绝对路径、
XML、MAC 和 partial 名称均由权威资源及平台生成。源文件必须是 regular file，
qemu-img 必须确认 qcow2/raw 且无外部 backing；执行前扫描其他 VM 引用并持有源 VM、
目标 VM、Pool 及全部源/目标文件锁。双 SSH relay 使用参数数组、输出限额、超时、
取消和双端独立审计，不在容器落盘。最终文件采用 hard-link no-overwrite 发布，
任何 hash/size/身份冲突都不得覆盖；失败仅删除本任务精确 partial。

## 安全验证

P7 Host Device 只接受同节点 ResourceIndex ID 且仅允许关机 VM。PCI 必须存在 IOMMU
group 并已由管理员预绑定 `vfio-pci`；Nexora 使用 `managed=no`，不得自动解绑宿主
驱动。预览和执行均重新扫描设备，按明确 PCI/USB 字段顺序比较身份，并检查其他 VM
引用；执行持有设备锁，身份、驱动、IOMMU 或可用状态变化即拒绝。

共享目录只接受 `NEXORA_SHARED_DIRECTORY_ROOTS` 中的索引，默认空列表。远端只执行
固定 `realpath -e --`，结果必须与配置根精确一致；不创建目录、不修改权限，也不接受
页面路径。Cloud Image IPv6 拒绝 unspecified、loopback、link-local、multicast、
跨子网 gateway 和重复地址；指标仅持久化聚合计数与 UTC 时间，远端失败局部降级，
不把 SSH 错误、原始输出、路径或凭据返回页面。

安全相关合并至少覆盖认证、CSRF、Host Key、命令编码、XML、路径、媒体 token、
任务幂等、网络回滚和节点零残留的定向测试。发现秘密时不得在输出中复述。
