# 平台媒体与存储设计

## 目录与索引

媒体服务只扫描配置后的 `/library` 子目录，支持 ISO、qcow2 和 raw。索引记录相对
路径、大小、mtime、SHA-256、类型、虚拟容量、backing chain、分类、架构和备注。

路径必须在规范化、符号链接解析后仍位于允许根目录。删除索引只删除数据库记录，
不得删除原文件。文件变化后旧索引和凭据进入 `stale`。

## ISO Range 服务

- 文件流式读取，不加载完整 ISO。
- URL 使用不可推导 credential ID，不暴露真实路径和文件名。
- 数据库只保存 token 哈希。
- token 可绑定媒体版本、节点、VM 和管理员，并支持吊销。
- token 是安装期长租约，不使用只有数分钟的普通页面令牌。
- 访问日志不得记录完整 token、query string 或 Authorization 值。
- 支持 `HEAD`、单字节 Range、`206`、`416`、`ETag` 和 `If-Range`。
- 首期可拒绝 multipart ranges，但响应必须符合 HTTP 语义。

生产环境优先 HTTPS。使用私有 CA 时必须由管理员显式配置远端信任；平台不得自动
修改节点 CA。无法安全访问时回退到目标节点缓存复制。

浏览器读取使用 Bearer，节点 QEMU 读取不得把 Bearer、cookie 或 query secret 写入
Domain XML。QEMU URL 仅包含非秘密 credential ID，服务端同时验证请求源 IP 与凭据
绑定的 host、VM、媒体 ID 和 SHA-256。Host.address 不是 IP 字面量时首期拒绝直连。

## ISO 远端缓存回退

- 固定目录为 `/var/tmp`，最终名为 `nexora-media-{sha256}.iso`。
- 任务 partial 含 Task ID；只清理本任务创建的 partial。
- 写入后验证大小和 SHA-256，以 hard link 无覆盖发布。
- 挂载前锁定节点上的精确缓存路径，并重新验证媒体索引版本。
- 首期只修改已关闭 VM 的 persistent XML，不隐式热换盘。
- 弹出后重新发现全部 Domain；存在任何引用时保留共享缓存。
- 零引用时仅删除通过严格命名校验的 Nexora 缓存文件。

Rocky 9.7 的 QEMU 10.1.0 实测即使安装 `qemu-kvm-block-curl`，HTTP block driver
仍可能被 vendor whitelist 拒绝。能力判断不能只依赖包存在或 Domain define 成功；
`qemu-img info` 也可能产生假阳性。Nexora 从 `virsh domcapabilities` 读取经过
严格路径校验的 system QEMU，以 machine-none、无默认设备和 QMP quit 执行临时
blockdev 探测；不创建 VM、不写远端文件。探测失败立即撤销凭据并使用缓存回退。

## 镜像复制

qcow2/raw 不得通过 HTTP 直接作为系统盘。任务先校验目标空间与同名冲突，再通过
SFTP/SCP 流式复制为任务唯一 `.partial` 文件，记录字节检查点，校验大小和 SHA-256，
可选执行 `qemu-img convert/resize`，最后在同一文件系统原子重命名。

禁止覆盖目标文件、修改平台原始镜像或默认使用其作为 backing file。失败只清理
本任务确认创建的临时文件；恢复前先验证远端临时文件和检查点。

## 存储范围

首期可写：

- libvirt dir Storage Pool
- libvirt NFS netfs Storage Pool
- 用户已挂载目录作为 dir Pool 纳管

其他 Pool 和 block/RBD/iSCSI 等卷只读发现并展示关联 VM。Nexora 不修改
`/etc/fstab`、不安装 NFS Client、不删除 NFS export 内容。

dir/netfs Pool 创建先生成 UUID 与安全 XML，远端 schema 校验后展示 Diff 和限时
确认。执行时持有 Pool 资源租约，重新扫描权威状态，再 define/build 并验证
active/autostart。Pool 配置 hash 排除 capacity、allocation、available 等统计值。

## 文件安全与引用

- 只允许已定义 Pool、VM XML 引用或用户显式授权目录中的路径。
- 创建前使用父目录和目标文件的安全解析，拒绝符号链接逃逸和路径穿越。
- 删除/扩容前重新读取 Pool、Volume key、路径、inode/设备和 VM 引用。
- 多 VM 共享、只读媒体、平台媒体和无法确认归属的文件禁止自动删除。
- Pool 删除默认只 undefine，不删除文件或 export 内容。
- undefine 前重新扫描 Domain，并按 file path 与 libvirt volume pool 双重检查引用。
