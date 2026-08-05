# Nexora 集成测试环境

## 专用节点

- SSH 别名：`test`
- 用途：Nexora 远端 KVM、故障注入和零残留集成测试
- 授权范围：可安装测试软件包、创建和删除测试虚拟机及测试资源
- 操作系统：Rocky Linux 9.7，x86_64（RHEL 兼容系）
- 登录用户：root
- 虚拟化：节点自身运行在 KVM 中，`/dev/kvm` 可用
- 资源基线：4 vCPU、约 4 GiB 内存、根文件系统约 94 GB 可用

### Ubuntu 26.04 LTS 测试节点

- 地址：`192.168.100.234`
- 用户：`ubuntu`
- 认证：SSH 私钥（`~/.ssh/id_ed25519`）
- sudo：免密 sudo
- 操作系统：Ubuntu 26.04 LTS，x86_64，内核 7.0.0-15-generic
- 虚拟化：libvirt 12.0.0，QEMU 10.2.1，`/dev/kvm` 可用
- 网络：`default` NAT 网络 active；`enp1s0`
- 存储：234 GB 可用，无已有 VM/Pool
- 资源基线：2 vCPU、7.4 GiB 内存
- 用途：全功能 KVM/libvirt 集成测试，可任意操作（创建/删除 VM、Pool、网络等）

仓库不得保存该节点的地址、私钥、密码或 SSH 配置。连接参数由操作者本机
`~/.ssh/config` 提供。

## 已验证状态

2026-07-28 使用非交互 SSH 实际验证：

- `ssh test` 可达，root 身份正常。
- `sudo -n true` 成功。
- `/dev/kvm` 存在。
- 节点虚拟化类型为 KVM。
- 初始探测时尚未安装 virsh、QEMU 和 libvirt 服务。

2026-07-28 已完成测试栈准备：

- libvirt 11.10.0，传统 `libvirtd` 服务模式。
- QEMU 10.1.0，`kvm_intel` 已加载。
- virt-install 5.1.0、qemu-img 10.1.0。
- OVMF 与 swtpm 已安装。
- `qemu-kvm-block-curl` 已安装，用于验证 HTTP block driver 能力边界。
- nfs-utils 2.5.4 已安装，`rpcbind` 与 `nfs-server` 仅作为测试夹具运行。
- `qemu:///system` capabilities、domcapabilities 和 nodeinfo 可读取。
- 已建立 `nexora-it-dir` dir Pool 和关机 VM `nexora-it-existing`。
- 回环 NFSv3 Export：`/srv/nexora-it-nfs`，包含业务保留验证文件。

NFS 工具由测试环境管理员依据测试授权安装，不是 Nexora 自动安装行为。Nexora
实现仍必须在缺少 NFS Client 时报告能力缺失并拒绝写入。

`qemu-kvm-block-curl` 同样由测试环境管理员安装。Rocky 的 QEMU 10.1.0 实测仍以
`Driver 'http' is not whitelisted` 拒绝启动 HTTP CD-ROM，证明包存在和 libvirt
define 成功不足以判定能力；Nexora 在该节点使用远端缓存回退。

## P7 Rocky 验证

2026-08-01 已完成：

- VM 与 Host 指标真实采样：1 test，12.59s。
- Cloud Image 静态 IPv6-only 与 IPv4/IPv6 双栈：2 tests，51.10s；完成镜像复制、
  NoCloud seed、VM 定义/启动、seed 内容恢复和零残留清理。
- 只读 virtiofs 共享目录：1 test，17.48s；完成授权根 `realpath` 复核、memfd/shared
  memory backing、libvirt 自动 PCI address 校验、卸载、原 Domain XML 和目录恢复。

当前 Rocky 节点的 IOMMU group 数量为 0，已发现 PCI 设备中没有同时满足
`vfio-pci` 与 IOMMU group 的隔离测试设备，因此 PCI 直通真实执行被硬件前置条件
阻塞。不得为完成测试修改内核启动配置、关闭安全机制或绑定随机业务设备。

## Host Key 约束

当前本机 `test` SSH 别名配置为不持久化 known_hosts，不能作为 Nexora Host Key
安全验收证据。Nexora 集成测试必须独立执行：

1. 获取并展示服务端 Host Key 类型与指纹。
2. 管理员确认后写入 Nexora 专用 known_hosts。
3. 使用严格 Host Key 校验重新连接。
4. 使用替换测试密钥验证 Host Key 变化会阻断连接。

不得为了测试修改 Nexora 的严格校验默认值。

## 密码 SSH 与普通用户 sudo

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_password_sudo.py
```

2026-07-29 结果：PASS，1 test，0.91s。测试以 root 私钥创建无 Home 的随机密码
临时用户，经 Nexora 专用 strict known_hosts、`AsyncSSHBackend` 和
`RemoteExecutor` 验证密码 SSH 与固定 `sudo -n -- id -u`。随机密码只经 stdin
传递且不进入审计；最终删除用户、sudoers、进程并验证三处临时目录残留为 0。
该夹具写 sudoers 只发生在测试环境管理员准备阶段，不是 Nexora 远端管理行为。

加密私钥口令入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_key_passphrase.py
```

2026-07-29 结果：PASS，1 test，2.50s。测试在内存生成加密 Ed25519 私钥和随机口令，
仅将公钥写入临时用户标准 authorized_keys；Nexora 经 strict known_hosts 和内存
私钥完成连接，审计不包含口令。最终用户、Home、进程及三处临时目录残留为 0。

## 测试资源命名与清理

- VM、Pool、Network 和临时文件统一使用 `nexora-it-` 前缀。
- 临时脚本仅位于 `/run`、`/tmp` 或 `/var/tmp`。
- 测试结束删除测试创建的 VM、磁盘、Pool 和 Network。
- 节点移除测试必须另行验证 Nexora 临时实体为零、业务测试资源仍存在。
- 每次执行前枚举同前缀残留，禁止基于宽泛路径或未解析变量清理。

## 恢复入口

真实集成测试入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_kvm.py
```

2026-07-28 结果：PASS，1 test，13.53s。已验证严格 Host Key、私钥 SSH、能力探测、
资源发现、已有 VM/Pool 纳管、raw 镜像复制、SHA-256、节点移除和零残留。移除后
VM、Pool 与复制文件仍存在；临时路径、unit、unit file、进程和监听均为 0。

Storage Pool 真实入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_storage.py
```

2026-07-28 结果：PASS，1 test，38.76s。已验证 dir 与 NFSv3 netfs 的 XML 校验、
define/build、启动、停止、refresh、autostart、undefine、带外 hash 稳定性和文件
保留。测试创建的 Pool、挂载和 Target 已清理，NFS Export 原始文件仍存在。

Storage Volume 管理入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_volume.py
```

2026-07-29 结果：PASS，2 tests，66.20s。已验证 revision 0012、远端
`storagevol` schema、dir 与 NFS netfs qcow2 无覆盖创建、8 MiB 到 16 MiB 扩容、
显式删除、Key/容量权威验证及动态统计 hash 稳定性。两个测试 Pool、Target 和 NFS
Volume 均已清理。

VM Disk 管理入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_vm_disk.py
```

2026-07-29 结果：PASS，1 test，31.65s。已在运行中的 `nexora-it-existing` 上验证
persistent qcow2 挂载、libvirt 自动 PCI address 接纳、设备卸载和 Volume 保留。
测试 Pool、Volume、Target 与 VM 测试磁盘引用均已清理。

VM CD-ROM 本地 ISO 入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_vm_cdrom.py
```

2026-07-29 结果：PASS，1 test，34.29s。已在运行中的 `nexora-it-existing` 上验证
已有 persistent CD-ROM 弹出、同节点 raw ISO 重新挂载和 config-only 写入。测试
结束恢复原始 VM XML，测试 Pool、ISO、Target 与 CD-ROM 均无残留。

平台 ISO 与缓存回退入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
NEXORA_INTEGRATION_MEDIA_BASE_URL=http://<nexora-address>:18084 \
uv run pytest -q tests/integration/test_remote_platform_iso.py
```

2026-07-29 最终结果：PASS，1 test，24.90s。已验证节点源 IP 绑定的单 Range
读取、凭据撤销后拒绝访问、system QEMU whitelist 预探测拒绝 HTTP 并自动转向
缓存、受控 `/var/tmp` 复制、大小/SHA-256、缓存 QEMU 启动及零引用删除。专用
VM、缓存文件和本地测试媒体服务监听均无残留。

## 模块化 libvirt 兼容

2026-07-29 将传统 `libvirtd` 临时切换为 `virtqemud`、`virtnetworkd`、
`virtstoraged`、`virtnodedevd` 与 `virtproxyd` socket activation，执行完整
`test_remote_kvm.py`：PASS，1 test，13.61s。首次夹具遗漏 `virtnodedevd` 导致
`discover.node_devices` 失败；补齐后 VM、Pool、Network、PCI/USB、镜像复制和
节点移除均通过。最终恢复传统服务，modular 单元 inactive，失败状态及临时
partial/socket/PID 均为 0；既有 VM、Pool 和复制文件保持存在。

## Debian 13 nested KVM 节点

2026-07-29 使用 Debian 官方 `debian-13-generic-amd64.qcow2` 创建 2 vCPU、2 GiB
的临时 nested KVM 节点。cloud-init 安装发行版官方 OpenSSH、sudo、libvirt
11.3.0 与 QEMU 10.0.11；`/dev/kvm`、普通用户免密 sudo 和传统 libvirtd 正常。
在 Debian 内预先定义关机 Domain `nexora-it-debian-existing`，通过一次性 SSH
本地转发运行：

```bash
NEXORA_DISTRIBUTION_HOST=127.0.0.1 \
NEXORA_DISTRIBUTION_PORT=10023 \
NEXORA_DISTRIBUTION_USER=nexora \
NEXORA_DISTRIBUTION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_distribution.py
```

结果：PASS，1 test，14.34s。验证两阶段 Host Key、普通用户 sudo、OS/libvirt/KVM
能力、宿主接口和已有 VM 自动发现。最终删除内外层测试 Domain、系统盘、seed ISO、
Tunnel 和临时文件，Rocky 原有 VM/Pool 保持存在。

QEMU Guest Agent 入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_vm_guest_agent.py
```

2026-07-29 结果：PASS，1 test，14.40s。测试定义仅含标准 Guest Agent channel 的
临时 VM，验证 shutoff 时不执行远端 Agent 命令，启动后无客户机 Agent 时显示
unavailable 且不泄露 stderr。最终 destroy/undefine，专用 Domain 无残留。

串口控制台入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_vm_serial_console.py
```

2026-07-29 结果：PASS，1 test，12.60s。对运行中的 `nexora-it-existing` 使用
严格 Host Key、内存私钥和固定 `virsh console --safe` 打开 AsyncSSH PTY，写入
回车后主动关闭。外部复核远端没有残留 `virsh console` 进程，VM/XML 未修改。

VNC/noVNC 代理入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_vm_vnc_console.py
```

2026-07-29 结果：PASS，1 test，10.83s。读取既有 VM 的回环 domdisplay，经
AsyncSSH local forward 和 Nexora 单次 websockify worker 获取 QEMU `RFB` banner。
连接结束后 manager 进程集合为空；Browser QA 进一步验证 noVNC canvas connected，
关闭页面后 ConsoleSession=closed 且容器无 worker 残留。

Snapshot 自动发现入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_snapshot_discovery.py
```

2026-07-29 最新结果：PASS，2 tests，36.91s。第一条在平台外通过 virsh 为专用
已关闭 qcow2 VM 创建 internal Snapshot，验证无需导入的发现；第二条通过 Nexora
独立预览、确认和 `vm.snapshot_change` 持久化任务创建原子内部快照，再通过独立
确认计划将 `qemu-io` 模式 B 恢复为快照前模式 A，再删除该 internal leaf；复核
parent/current、配置 hash、目标消失和 VM 保留。两轮 Snapshot、VM 定义和 8 MiB
磁盘均已精确清理。

VM 实时性能入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_vm_metrics.py
```

2026-08-01 用例已扩展为同时读取 Host `/proc/loadavg`、`/proc/meminfo`、
`/proc/uptime` 和既有测试 VM `virsh domstats`，验证负载、内存、运行时间、状态及
CPU/磁盘/网络非负差分速率；全程只读，不创建远端资源。

VM managed Volume 导入创建入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_vm_create.py
```

2026-07-29 最新结果：PASS，1 test，22.05s。使用现有 `nexora-it-dir` 创建专用
64 MiB qcow2 与 1 MiB raw `.iso`，并选择 active/persistent `default` Network，
经 revision 0014 计划与 `vm.create` 任务定义 BIOS VM。验证 UUID、内存、vCPU、
VirtIO 系统盘/网卡、自动 MAC、readonly SATA CD-ROM 和 shutoff 后实际启动；
Network hash 保持不变。随后精确清理 VM、系统盘和 ISO，三者均不存在。

平台镜像复制后创建 VM 入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_vm_media_create.py
```

2026-07-29 最新结果：PASS，1 test，24.28s。将本地 8 MiB raw 平台镜像通过 SSH
流式复制到 `nexora-it-dir`，验证大小/SHA-256、Pool refresh、Volume 自动发现、
revision 0015 可恢复任务、VirtIO 系统盘、计划 MAC 和 `default` Network。任务使用
节点已有 genisoimage/xorriso 生成 hostname、用户、SSH 公钥、SHA-512 crypt 密码
及静态 IPv4 NoCloud seed，并再次走已发布 seed 内容哈希恢复路径。复制后系统盘
通过 revision 0018 从 8 MiB grow 到 16 MiB 并复核容量/SHA。VM shutoff 后实际
启动成功；测试 VM、系统盘、seed 与 partial 随后精确删除，均不存在。

关机完整克隆入口：

```bash
NEXORA_INTEGRATION_HOST=<address> \
NEXORA_INTEGRATION_PRIVATE_KEY_FILE=<private-key-path> \
uv run pytest -q tests/integration/test_remote_vm_clone.py
```

2026-07-29 结果：PASS，1 test，25.47s。创建专用 32 MiB qcow2 与关机 persistent
源 VM，通过 revision 0017 计划、双 SSH relay 和 `vm.clone` 持久化任务生成新
UUID/MAC 与独立磁盘；验证两端 SHA-256 一致、未知 metadata 保留、目标实际启动、
源端保持。清理后源/目标定义、磁盘和 task partial 均不存在。当前仅同节点实测；
跨节点需第二台 KVM 节点后补矩阵。
