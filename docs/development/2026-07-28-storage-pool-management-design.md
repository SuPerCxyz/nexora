# Storage Pool 管理设计

状态：2026-07-28 已实现并通过真实 Rocky/NFS 验证。

## 目标

为已发现及新建 libvirt `dir`、NFS `netfs` Pool 提供结构化预览、确认、异步执行与
写后验证。其他 Pool 继续只读展示。

## 方案选择

采用 `RemoteExecutor + virsh + 安全 XML builder`。libvirt-python 继续用于本地
XML/能力辅助，不直接替代 SSH 认证；不使用 libvirt TCP，不向节点落盘 Nexora
脚本。

放弃直接拼接 virsh shell 命令和远端长期 helper。所有参数经 `CommandSpec`，
XML 通过 stdin 传递。

## 支持操作

- 创建 dir Pool。
- 创建 NFS netfs Pool，支持 NFSv3/v4 与受限 mount option。
- start、stop、refresh、autostart enable/disable。
- undefine，仅删除 libvirt 定义。

不删除 target path、卷、NFS 文件或 export，不修改 `/etc/fstab`，不安装 NFS
Client。运行中或被 VM 引用的 Pool undefine 必须阻断。

## 持久化确认计划

`StoragePoolChangePlan` 保存：

- host、operation、Pool UUID/name/type。
- 已有资源 ID、generation、persistent hash。
- 结构化输入摘要、当前/目标 XML 与 Diff。
- confirmation digest、10 分钟有效期、状态和错误。

创建计划时生成 Pool UUID。确认 token 只显示一次，数据库只存 digest。

## 执行流程

1. 验证输入、路径、NFS Server/Export 和 mount option。
2. 只读检查 Pool 名称、UUID、target path 冲突。
3. 生成 XML并远端 schema 校验。
4. 展示 XML/Diff、风险和不会删除的数据。
5. 管理员确认后创建持久化任务。
6. 获取 `host + storage_pool + native_id` 租约锁。
7. 再次扫描 Pool 与 Domain；校验 base hash 并阻断 VM 磁盘引用。
8. 执行单一 virsh 写操作。
9. 重新读取 Pool 或确认已 undefine。
10. 更新 ResourceIndex、任务步骤与审计，释放锁。

数据库事务不得跨远端 I/O。

## 路径与 NFS 安全

- target path 必须是绝对规范路径，不含 NUL、`.`、`..`，长度受限。
- 拒绝 `/`、`/etc`、`/usr`、`/boot`、`/proc`、`/sys`、`/dev`、`/run` 等系统根。
- Pool 名称使用受限字符集；NFS Server 复用主机名/IP validator。
- Export 必须是绝对 POSIX 路径。
- mount option 仅允许 `ro/rw,soft/hard,timeo,retrans,rsize,wsize` 的安全子集；
  禁止命令字符和任意 option。
- NFSv3/v4 通过独立结构化字段生成 `<protocol ver>`，不接受 `vers=` 绕过。

## 恢复

创建中断后先按计划 UUID 查询远端：定义与目标 XML一致则幂等成功；不存在则允许
显式重试；不一致则进入冲突。生命周期操作同样先验证最终状态再决定是否重试。
不得启动时盲目重放。

## 测试

- XML builder、路径、NFS/mount option、确认 token、过期和带外冲突。
- virsh 参数、资源锁、写后验证、undefine 不删除内容。
- Rocky `test` 节点 dir Pool 创建/生命周期/undefine。
- 隔离 NFS export 的 netfs 创建、使用和保留内容。

真实测试同时确认 `virt-xml-validate -` 的 stdin 兼容入口，以及 Pool 配置 hash
必须排除 capacity、allocation、available 等易变统计字段。
