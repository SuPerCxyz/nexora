# 平台镜像复制后创建虚拟机设计

## 目标

允许管理员从 `/library` 中已索引的 qcow2/raw 镜像创建关机状态的 persistent VM。
镜像必须先完整复制到目标节点的 managed dir/netfs Pool，不能直接远程运行，
也不能使用平台原镜像作为 backing file。

## 边界

- 页面只提交 `MediaItem`、目标 Pool、Network 和本地 ISO 的资源 ID。
- 目标文件名使用受限 basename，格式扩展名必须与源镜像一致。
- 不覆盖同名文件；复制使用任务专属 `.partial`、大小和 SHA-256 校验后原子发布。
- 首期不执行 `qemu-img convert`、扩容、cloud-init、UEFI 或自动启动。
- 复制完成后刷新 Pool/Volume 索引，再以新 Volume 定义 VM。
- 失败只自动清理本任务 `.partial`；已校验发布的最终镜像保留，供安全恢复或人工处理。

## 持久化计划

新增独立 `vm_media_creation_plans`，保存 Host、Media SHA、Pool generation/hash、
目标文件名、VM UUID、Network/ISO 版本、结构化输入、目标 XML、Diff、
10 分钟确认摘要、状态、结果资源和错误。

不复用 managed Volume 创建计划，避免把尚未存在的目标文件伪装成 ResourceIndex。

## 任务与恢复

`vm.create_from_media` 使用一个可恢复任务：

1. 重读 Media、Pool、Network、ISO 和 Domain 权威状态；
2. 复制并校验镜像，或识别同 SHA 的已发布目标；
3. refresh Pool，发现并验证新 Volume；
4. 校验 XML 并定义 persistent VM；
5. 重扫 Domain，验证 UUID、磁盘、网络和 ISO。

恢复时每次从权威状态重新判定：目标不存在则复制；任务 partial 存在则清理后重试；
最终文件 SHA 匹配则跳过；VM 完全匹配则成功；任何碰撞不匹配均阻断且不覆盖。

## 锁与验证

- 任务全程持有目标文件身份锁和 VM UUID 锁；复制阶段沿用 Pool UUID 锁。
- 本地 ISO 使用 Volume 锁；锁租约由任务协调器心跳续租。
- 单元覆盖输入、确认、恢复、碰撞、XML 与锁；Web 覆盖候选和任务提交。
- 真实 Rocky 覆盖复制、发现、定义、启动，以及 VM 和测试磁盘精确清理。
- 完成前运行 pytest、Ruff、mypy、diff check、单容器和 375px Browser QA。
