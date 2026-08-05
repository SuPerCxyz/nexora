# Cloud Image 与 cloud-init 创建设计

## 已完成能力

在已完成的平台 qcow2/raw 复制创建流程上增加 NoCloud seed：

- Linux Cloud Image 仍完整复制到目标 managed dir/netfs Pool。
- 支持 hostname、普通用户名、SSH 公钥、SHA-512 crypt 密码、DHCP 和静态 IPv4。
- 支持复制后 grow-only 系统盘扩容；仍不支持 UEFI、IPv6 或自动启动。
- 用户数据只存在于确认计划和 seed ISO；页面、任务摘要和日志不回显完整内容。

## Seed 生成

远端必须已有 `genisoimage`/`mkisofs` 与 `xorriso`/`isoinfo` 兼容工具；Nexora
只探测，绝不自动安装。通过固定 `bash -s` 脚本在
`/var/tmp/nexora-cloudinit-{task_id}` 创建权限 0700 的临时目录：

1. 从敏感环境变量解码固定的 `user-data`、`meta-data`、`network-config`；
2. 以 volume label `cidata` 生成任务专属 partial ISO；
3. 使用 hard link 无覆盖发布到 Pool 中 VM UUID 派生的 seed 文件；
4. trap 清理临时目录与 partial。

脚本和所有路径由平台生成；页面不能提交脚本、目录或 seed 路径。

## 恢复与验证

- 计划保存三份配置的 SHA-256，不保存 SSH 私钥。
- 最终 seed 已存在时，使用只读 ISO 工具提取三份文件并在内存中比较 SHA-256。
- 不匹配即阻断；不覆盖或删除碰撞文件。
- Domain XML 将 seed 作为 readonly SATA CD-ROM 挂载，系统盘仍为 VirtIO。
- 写后验证 VM、系统盘、seed 路径、网络和关机状态。
- 失败仅清理本任务临时目录和 partial；已发布 seed 保留以便恢复。

## 第二切片：密码、静态 IPv4 与扩容

密码在 Web 请求线程内立即通过固定 `openssl passwd -6 -stdin` 生成
shadow-compatible SHA-512 crypt hash。持久化
计划、任务、日志和 NoCloud seed 只保存 hash，不保存可解密明文；SSH 公钥与密码
至少提供一种。`ssh_pwauth` 和 `lock_passwd` 由是否配置密码派生。

静态 IPv4 只接受结构化 CIDR、同子网 gateway 和最多三个 IP 形式 DNS。拒绝
loopback、link-local、multicast、unspecified、IPv6 gateway、任意 YAML 和重复 DNS。
NoCloud network-config v2 使用计划 MAC 匹配；DHCP 与静态模式互斥。

目标容量以 GiB 结构化输入，必须不小于平台镜像 virtual size 且不超过 16 TiB。
完整复制及源 SHA-256 校验后才允许固定 `qemu-img resize` grow；随后重新读取 virtual
size。恢复时目标已等于计划容量时，还必须与 revision 0018 持久化的扩容后 SHA-256
一致，才能跳过复制与扩容；仍等于源容量可继续 grow，其他容量一律冲突。扩容不
承诺自动增长客户机文件系统。

## 仍待后续

UEFI、Secure Boot、TPM、Windows、IPv6 静态网络和自动启动仍在后续切片。
