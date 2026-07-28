# 远端管理与 SSH 设计

## 唯一入口

所有远端行为必须经过 `RemoteExecutor` 策略入口。业务模块不得创建裸 SSH
连接、拼接 Shell、直接处理凭据或绕开统一审计。

建议接口以 argv、stdin、超时、敏感标记、operation ID 和取消令牌为核心。
SSH 最终编码为远端命令字符串时，必须使用统一 POSIX quoting。

## 职责矩阵

| 场景 | 首选机制 | 说明 |
|---|---|---|
| 主机能力与网络探测 | SSH 命令适配器 | 标准命令，只读优先 |
| libvirt 查询和写入 | SSH + 远端 `virsh -c qemu:///system` | 首期主路径 |
| libvirt 补充能力 | libvirt-python `qemu+ssh` | 经 ADR 验证后启用 |
| 文件复制 | SFTP/SCP 流式传输 | rsync 仅探测后增强 |
| XML 校验 | 远端 `virt-xml-validate` | 缺失时明确降级 |
| 图形/串口控制台 | 按需 SSH Tunnel | 不改变远端监听 |

任何底层机制都必须复用相同凭据、Host Key、并发、取消和脱敏策略。

## 命令安全

- 业务层只能调用 typed command adapter，不得传 shell fragment。
- 参数独立编码；目标程序支持时用 `--` 结束选项。
- 环境变量名采用白名单正则，值单独编码。
- 管道、重定向和脚本只能来自版本控制内的固定模板。
- 复杂脚本通过 `bash -s` 或 `python3 -` 的 stdin 临时执行。
- 临时文件只在 `/run`、`/tmp`、`/var/tmp`，使用随机 Nexora 前缀和 trap 清理。
- 禁止 ProxyCommand、LocalCommand、任意 URI query 和用户控制的 SSH 配置注入。
- stdout/stderr 分离并限额；截断必须显式标记。

## 认证与 sudo

- 支持 SSH 密码、私钥、加密私钥、自定义端口。
- 首期普通用户只支持经验证的 `sudo -n` 非交互 sudo。
- SSH 密码不得自动复用为 sudo 密码。
- 不支持需要 TTY、MFA 或交互提示的 sudo。
- qemu+ssh 不能满足认证和审计要求时必须回退到远端 virsh 主路径。

## Host Key

首次连接只读取并展示目标、端口、算法、指纹和历史记录，用户确认后建立信任。
Host Key 变化必须阻断连接并同时展示旧、新指纹。禁止静默接受或自动覆盖。

节点移除时删除活跃信任和连接材料，但保留不可变审计 tombstone；该记录不能作为
新连接的自动信任依据。

## 节点预检查与移除

添加节点先只读检查 SSH、身份、sudo、OS、架构、KVM、libvirt、QEMU、网络、
存储、NFS 和媒体可达性。不得自动安装或修复远端软件。

移除节点只清理 Nexora 管理记录、临时脚本、瞬态 unit、隧道、socket 和任务。
不得删除 VM、磁盘、Pool、NFS、libvirt 网络、Bridge、VLAN、IP 或路由。

