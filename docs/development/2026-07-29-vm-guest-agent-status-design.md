# QEMU Guest Agent 状态设计

## 目标

在 VM 详情页按需显示 Guest Agent Channel、响应状态、Guest Hostname 和 IP。
Nexora 不进入客户机、不安装 Agent，也不把高频结果写入 SQLite。

## 采集

- 页面通过认证 HTMX 请求按需采集，默认 15 秒刷新。
- 仅对运行中 VM 执行固定 `virsh qemu-agent-command --timeout 5`。
- 命令固定为 `guest-ping`、`guest-get-host-name`、
  `guest-network-get-interfaces`，不接受页面 JSON 或参数。
- Persistent/live XML 仅用于判断 `org.qemu.guest_agent.0` Channel 是否配置。
- Agent 未安装、未响应或命令不支持时局部降级，不影响 VM 详情页。

## 解析与隐私

- JSON 最大 1 MiB；接口最多 256 个，每接口最多 64 个地址。
- Hostname、接口名、MAC 和地址均限制长度并校验 IP/MAC 格式。
- 默认过滤 loopback、link-local 和未指定地址；保留 IPv4/IPv6 与 prefix。
- 不展示原始 Agent JSON、错误 stderr、磁盘/用户/进程等额外客户机信息。
- 不持久化 Guest hostname/IP，不写任务输出或审计正文。

## 状态

- `not_configured`：XML 无 Guest Agent Channel。
- `stopped`：VM 未运行。
- `unavailable`：Channel 存在但 Agent 不响应。
- `connected`：guest-ping 成功；其他可选命令失败时仍显示部分结果。
