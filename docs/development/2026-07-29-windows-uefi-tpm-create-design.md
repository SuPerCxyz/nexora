# Windows ISO、UEFI、Secure Boot 与 TPM 创建设计

## 目标与范围

扩展现有 revision 0014 managed Volume 创建链，而不是建立第二套 Windows 服务。
首切片支持 Linux/Windows Profile、BIOS/UEFI、可选 Secure Boot、TPM 2.0 emulator、
Windows OS ISO、可选 VirtIO Driver ISO、VirtIO/SATA 系统盘及 VirtIO/e1000e 网卡。
仍只定义 persistent shutoff VM，不自动进入客户机安装软件，不自动安装宿主机包。

## 方案比较与决定

1. 只用 `<os firmware='efi'>`：XML 简洁，但旧 libvirt/固件 metadata 不完整时失败。
2. 硬编码发行版 OVMF 路径：实现快，但违反动态探测和多发行版兼容门禁。
3. 能力驱动双路径：优先 libvirt firmware autoselection；不可用时仅使用
   `domcapabilities` 返回的绝对 loader，并在同目录匹配可读 VARS 模板。

采用方案 3。能力不足、路径不安全或模板不唯一时拒绝预览，不猜测、不安装软件。

## 结构化输入

通用创建输入增加：

- `guest_profile`: `linux` 或 `windows`
- `firmware`: `bios` 或 `uefi`
- `secure_boot`: boolean；仅 UEFI
- `tpm2`: boolean
- `disk_bus`: `virtio` 或 `sata`
- `network_model`: `virtio` 或 `e1000e`
- 第二 ISO 的 Resource ID、native ID、generation、hash、key 和 name

Windows 默认 UEFI、VirtIO 系统盘、e1000e 网卡；VirtIO Driver ISO 可选。所有 ISO
仍只接受同节点 active managed dir/netfs Pool 中的 raw `.iso` Volume。页面不能提交
路径、loader、NVRAM、machine、TPM socket 或 XML。

## 能力探测

`VmCreationRemote` 一次读取 `virsh domcapabilities`，安全解析：

- architecture 与 firmware autoselection；
- loader `pflash`、readonly、secure 枚举及绝对路径；
- TPM model、backendModel=emulator、backendVersion=2.0。

TPM 额外使用固定 `command -v swtpm` 只读确认。手工 UEFI fallback 只接受
domcapabilities 返回且远端可读的 loader；VARS 模板只能从 loader 同目录、固定
CODE→VARS 名称映射中选择并复核可读 regular file。不得扫描整个文件系统。

## XML 与 NVRAM

自动模式生成 `<os firmware='efi'>` 及明确 firmware feature。fallback 生成只读
pflash loader。NVRAM 目标位于所选 Pool 中平台派生的
`.nexora-nvram-{vm_uuid}.fd`，模板来自能力探测；任务持有该文件身份锁。
TPM 生成 `tpm-crb`（能力不可用则 `tpm-tis`）与 emulator 2.0 backend。

Windows 安装 ISO 与 Driver ISO 使用不同 readonly SATA CD-ROM target。系统盘总线、
网卡 model 只由枚举字段生成。保存前执行远端 schema 校验，定义后重新读取 XML，
验证 libvirt 规范化后的 loader、NVRAM、TPM、磁盘、网卡和两张 ISO。

## 冲突、恢复和清理

确认计划继续保存完整结构化输入、XML 和 Diff。执行前重新读取 VM、Pool、Volume、
Network 与 domcapabilities；任一 generation/hash/能力变化都阻断。锁顺序为全部
Volume native ID、NVRAM 文件身份、VM UUID。

恢复仍为 verify-only：只有既有 VM 与计划固件、设备及资源引用完整匹配才成功。
失败不得 undefine VM、删除系统盘/ISO、覆盖 NVRAM 或清理 TPM state。尚未启动时
NVRAM 目标可以不存在；启动后由 libvirt 从模板初始化。

## 测试与首期验收

- 单元：输入组合、双 ISO 身份、domcapabilities、fallback 路径、XML、TPM、未知值。
- 安全：伪造 loader/VARS、Secure Boot 能力缺失、swtpm 缺失、跨节点 ISO、路径注入。
- Web：结构化表单、Diff 无路径输入、375/1280px、44px、无秘密或控制台错误。
- Rocky：定义并启动 UEFI Windows Profile 测试 VM，挂载两张 ISO，验证 TPM 2.0；
  当前节点 Secure Boot 能力为 `secure=no`，必须验证预览拒绝。
- 清理：只删除测试 VM/测试 Volume；Nexora 不修改固件包、宿主安全设置或业务资源。
