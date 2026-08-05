# 关机虚拟机完整克隆设计

## 首期范围

支持 persistent、shutoff VM 的 file 类型 qcow2/raw 完整克隆，可选择同节点或另一
已纳管节点的 active managed dir/netfs Pool。生成新名称、UUID、MAC，复制全部可写
文件磁盘和 NVRAM；默认不启动、不自动启动，不使用 backing/reflink/硬链接。

拒绝 transient、运行中、managed-save、外部快照链、block/network 磁盘、共享可写
磁盘、Host Device、架构不兼容和目标 Bridge/Network 缺失。readonly CD-ROM 不复制；
平台媒体引用在目标节点不可用时阻断并说明。

## 计划与身份

revision 0017 保存 source host/VM UUID/hash、target host/Pool UUID/hash、新 UUID/MAC、
每个源文件身份与目标 basename、目标 XML、Diff、限时确认摘要和状态。页面只提交
资源 ID、新名称与目标 basename 前缀，不提交源/目标绝对路径或 XML。

目标路径由权威 Pool target 和平台生成 basename 派生。文件锁按 host+规范路径排序，
VM 锁按 host+UUID 排序；源 VM、目标 VM、源 Volume/文件和目标 Pool 均在执行前刷新。

## 远端到远端传输

- 两端分别使用 ManagedHostConnectionResolver 与严格 Host Key/内存凭据。
- AsyncSSH 双会话分别执行固定 `dd` reader/writer，stdout 直接流向 stdin；不在
  Nexora 本地落盘，也不依赖远端 Nexora 脚本。
- 1 MiB chunk，周期回调保存文件/总字节进度、心跳和 checkpoint。
- 开始前 `stat` 只接受 regular file 并记录 size，symlink 会被拒绝；目标同名阻断。
- 完成后比较 size 与两端 SHA-256，再以 hard-link 无覆盖发布并删除本次 partial。
- 同节点也走独立读写句柄，不使用 reflink、hardlink clone 或 backing file。
- 中断重试清理任务专属 partial 后重复制当前文件；已发布文件必须 size/SHA 完整
  匹配才复用，不完整或异内容目标一律阻断。

## XML

在安全 lxml 文档上局部修改 name、UUID、磁盘 source、MAC 和 NVRAM；保留 description、
未知元素/属性和既有 device address，仅移除自动生成的网卡 target 名称。libvirt
autostart 是 Domain XML 外状态，目标 define 后保持默认关闭。目标远端 schema 校验
后才确认。

## 任务与失败

`vm.clone` 为可恢复任务：预检、逐文件复制、目标 define、权威验证。每个文件一个
TaskStep 并在 checkpoint 保存 source/partial/final/size/SHA/status。失败只删除当前
任务 partial；已发布文件和已定义目标 VM 保留供 verify/manual，不自动删除源或
重放 define。源 VM 与磁盘永不修改。

## 验证

- 单元：XML 未知项保留、新 UUID/MAC、路径派生、共享/链/设备拒绝。
- 传输：双 AsyncSSH、symlink/碰撞、进度、SHA、中断恢复和无本地落盘。
- 任务：幂等、锁序、重启 checkpoint、define 不明确时 verify-only。
- Rocky：同节点完整复制、启动目标、源保持、零 partial 已通过；双节点待环境具备。
- Browser：Diff、逐文件进度、375px、危险提示与无路径注入。
