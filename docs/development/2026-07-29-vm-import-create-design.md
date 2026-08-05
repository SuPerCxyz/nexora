# 从 managed Volume 创建 VM 设计

## 首个切片

从同节点现有 qcow2/raw Storage Volume 定义一台新的关机 persistent VM。此切片：

- 不复制、转换、扩容或删除磁盘。
- 不自动启动 VM。
- 不接受任意路径，磁盘必须来自 ResourceIndex。
- 仅支持 BIOS，UEFI/TPM/Secure Boot 后续扩展。
- 首期不添加网卡；网络选择在后续创建切片接入。

## 方案选择

1. 直接生成 Domain XML 并 `virsh define`：Diff 完整、未知默认由 libvirt 写后读取，采用。
2. `virt-install --import`：参数组合隐式生成 XML，预览与精确验证较弱，不采用。
3. 先复制镜像再定义：属于平台镜像创建流程，不与已有 Volume 导入混合。

## 权威预检

预览和执行前均：

1. 刷新 Storage 与 Domain 全量索引。
2. 验证 Pool 为 active managed dir/netfs。
3. 验证 Volume 为 managed qcow2/raw、绝对路径且 hash 未变化。
4. 验证 Volume 未被任何现有 VM 引用。
5. 验证 VM 名称和生成 UUID 均不存在。
6. 读取 `virsh domcapabilities`，只接受 x86_64/aarch64。

名称只允许安全 ASCII 标识；内存与 vCPU 有明确上下限。页面不能提交磁盘路径、libvirt
URI、emulator 或任意 XML。

## XML

结构化生成最小 Domain：

- `domain type=kvm`、随机 UUID、memory/currentMemory、static vCPU。
- `<os><type arch=...>hvm</type><boot dev=hd/>`，BIOS。
- CPU 使用 host-model；x86_64 启用 ACPI/APIC，aarch64 启用 ACPI。
- file Disk 使用权威 path/format，target vda/virtio。
- pty serial/console、virtio Guest Agent channel。
- VNC autoport 仅监听远端 127.0.0.1，供后续 SSH tunnel 使用。
- balloon virtio，生命周期策略 destroy/restart/destroy。

XML 由 lxml 构造，使用 `virt-xml-validate - domain` 远端校验，页面展示完整创建 Diff。

## 持久化计划与恢复

revision 0014 新增 `vm_creation_plans`，保存 host、Volume 双身份、生成 VM UUID、
结构化输入、proposed XML、Diff、确认摘要、状态和结果 resource ID。

三步任务持有 Volume 与目标 VM UUID 双锁：

1. 刷新并复核 Volume、引用、名称、UUID 和 domcapabilities。
2. `virsh define /dev/stdin --validate`。
3. 重新发现并验证 persistent VM 名称、UUID、磁盘 path/format 和核心 XML。

若任务中断后目标 UUID 已存在，只有完整匹配计划才标记成功；否则冲突。失败时不自动
undefine VM，也不删除或修改 Volume。恢复策略为 verify_only。

## 验收

- 单元：输入、XML、架构、名称/UUID冲突、Volume 引用、带外 hash、确认与恢复。
- Web：CSRF、结构化预览、任务提交、无路径字段和技术字体。
- Rocky：创建专用 qcow2，Nexora define、发现、启动条件验证，随后只清理测试 VM/盘。
