# VNC/noVNC 控制台设计

## 范围

为已有 VNC graphics 的运行中 VM 提供 noVNC 页面。浏览器只连接 Nexora 现有 HTTP
端口；远端 VNC 不改监听、不开放防火墙、不建立永久 Tunnel。SPICE 只展示限制，
本切片不自动转换 XML。

## 目标发现

- 使用固定 `virsh domdisplay <UUID> --type vnc` 读取运行时 endpoint。
- 仅接受 `vnc://127.0.0.1:<display>`、`vnc://localhost:<display>` 或明确数字端口。
- display 转换为 TCP 5900+display，范围限制 5900..65535。
- live XML 必须存在 VNC graphics；password/listen/socket 等原始字段不进入页面。
- 首期拒绝配置 VNC password 的 VM，避免把既有业务秘密复制到浏览器。

## 传输

1. ConsoleSession 以 `vnc` kind 创建，沿用 60 秒 token 和 Session/Origin 绑定。
2. claim 后建立 AsyncSSH `direct-tcpip` 本地转发到远端回环 VNC。
3. 为该会话启动 Nexora 单次 websockify loopback 子进程，目标是 Tunnel 本地端口。
4. FastAPI 使用 loopback WebSocket client 连接 websockify，并与浏览器双向桥接。
5. noVNC RFB 使用 `binary` 和额外 token subprotocol；服务端仅回显 `binary`。
6. 任一侧关闭即终止 websockify 进程组、SSH forward 和连接，更新 ConsoleSession。

动态端口只绑定 127.0.0.1，不映射到 Docker Host。websockify 命令无用户输入，
由管理器分配端口；stderr 有界且不展示。Tini 回收意外孤儿，应用 shutdown 先由
控制台管理器终止已登记子进程。

不使用 PyPI websockify：0.13.0 会强制引入 Redis 客户端，违反最高产品门禁。
worker 基于已锁定的 websockets 实现最小二进制 WebSocket↔TCP 功能。

## 页面

noVNC 1.7.0 在构建阶段本地复制并以 ES module 加载。页面支持缩放、全屏、发送
Ctrl-Alt-Delete、基础剪贴板与连接状态；默认 shared=false。Token 在构造 RFB 后
立即从 DOM 删除。

## 验证

- parser：合法 display、IPv6/非回环/socket/越界/password 拒绝。
- manager：loopback 端口、固定 argv、run-once、子进程组关闭和 SSH forward 清理。
- WebSocket：Session/Origin/kind/单次 token、binary subprotocol、帧上限。
- Rocky：既有 VM VNC RFB 握手、页面关闭、Tunnel/websockify/Session 零残留。
- Browser：375/1280px、全屏/组合键、无 Token URL、无控制台错误。
