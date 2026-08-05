# 控制台、克隆与关机迁移

## 控制台

浏览器通过一次性 WebSocket token 连接 Nexora proxy，再经按需 SSH Tunnel 到远端
回环 VNC 端口。不得永久修改 VNC 监听或开放公网端口。

token 绑定管理员 Session、host、VM 和用途，短时有效且只保存哈希。WebSocket 必须
校验 Origin。页面关闭、空闲超时、节点移除和容器退出时清理 tunnel/proxy。

已有 SPICE 只读识别。转换 VNC 必须显式请求、展示 XML Diff 并遵循冲突检测。
串口使用 xterm.js，复用相同认证、并发、审计和清理策略。

## 完整克隆

克隆生成新 UUID 和 MAC，复制全部文件磁盘及 NVRAM，不使用 backing-file 链接克隆。
复制前检查目标架构、存储、空间与同名冲突；每个文件和总任务均展示进度并校验。
revision 0017 计划绑定源 VM hash、目标 Pool hash、派生路径和目标 XML。双 SSH relay
只在内存中转发 1 MiB chunk；任务 partial 经 size/SHA-256 后无覆盖发布。失败不删除
源或已发布最终文件，恢复只复用内容完全匹配的目标。详细实现边界见
`docs/development/2026-07-29-vm-full-clone-design.md`。

## 关机迁移

首期只允许关闭状态、file 类型 qcow2/raw、本地目录或 NFS 目录。block、RBD、
iSCSI 和复杂外部快照只展示限制。

流程：

1. 重新确认 VM 关闭并读取 persistent XML。
2. 枚举磁盘、NVRAM、Host Device 和其他文件依赖。
3. 验证目标架构、CPU、Bridge、存储和空间。
4. 生成目标 XML 和文件映射并展示 Diff。
5. 使用可恢复文件任务复制并校验。
6. 在目标节点定义并重新读取验证。
7. 默认不启动目标 VM。

默认保留源定义和源磁盘。由于源、目标可同时存在相同 UUID，资源身份必须包含
`host_id`，页面必须持续警告两端不可同时启动。

源端清理是独立危险操作，必须逐项确认定义、磁盘和 NVRAM；不得作为迁移成功的
隐式步骤。
