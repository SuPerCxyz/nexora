# 控制台会话与串口首切片设计

## 范围

首切片实现 VM 详情页创建一次性串口会话、xterm.js 页面和 FastAPI WebSocket 到
AsyncSSH `virsh console` 的双向桥接。VNC/noVNC 复用同一会话模型，但在下一切片
接入按需 SSH Tunnel 与 websockify。不得改变远端 XML、监听地址或防火墙。

## 方案

选择 Python 主进程内的 WebSocket/AsyncSSH 串口桥接。相比为串口启动 websockify，
该方案直接支持 PTY、窗口尺寸与双向字节流，且不增加常驻进程。相比浏览器直连，
认证、Host Key、审计和并发限制仍由 Nexora 控制。

## ConsoleSession

- UUID 标识；token 只显示一次，SQLite 仅保存 SHA-256 摘要。
- 绑定管理员 Session hash、host ID、VM UUID 和 `serial` 用途。
- 状态为 pending、active、closed、expired、interrupted。
- pending 最长 60 秒；首次 WebSocket 原子 claim，禁止重放。
- active 记录最近活动；空闲 5 分钟、硬上限 60 分钟。
- 启动时将遗留 active 标记 interrupted；节点移除级联删除本地记录。

## Web 安全

- POST 创建会话，要求当前 Session、CSRF、VM 存在且有 serial/console PTY。
- token 不进入 URL/query/cookie；页面仅在首次 POST 响应内存中持有。
- WebSocket path 只有 Session UUID；token 放在 `Sec-WebSocket-Protocol`。
- 握手同时验证 HttpOnly Session Cookie、管理员 Session hash 和严格 Origin。
- 不记录 token、终端内容、客户机输入或完整 subprotocol。

## 远端与桥接

- remote 层提供专用 `SerialConsoleConnector`，业务层不得拼接 Shell。
- 使用现有 ManagedHostConnectionResolver、known_hosts 和内存凭据。
- 固定参数为 `virsh -c <host URI> console <canonical UUID> --safe`。
- AsyncSSH 请求 xterm PTY；WebSocket 单帧和 SSH 单次读取均限制 64 KiB。
- 任一侧关闭、超时、取消或异常时关闭 SSH process/connection 并持久化终态。
- 应用 shutdown 先拒绝新会话，再关闭活动桥接。

## 前端

- xterm.js 与 fit addon 在 Node 构建阶段固定版本并复制到本地静态目录。
- 页面默认浅色主题，终端区域使用等宽字体；连接、断开和错误均有文字状态。
- 浏览器关闭触发 WebSocket close；重载不会复用一次性 token。

## 验证

- 单元：token 摘要、过期、原子 claim、Session/Origin 绑定和启动恢复。
- Web：CSRF、VM capability、token 不出 URL、未认证 WebSocket 拒绝。
- 桥接：本地 AsyncSSH PTY 双向字节、帧上限、关闭和敏感审计。
- Rocky：临时/已有 VM 串口握手、主动关闭及无进程/socket/session 残留。
- Browser：xterm 本地加载、375px 无横向溢出、无控制台错误。
