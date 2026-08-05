# VM Disk 设备管理设计

## 目标

在现有 VM 详情页结构化展示和管理 libvirt Disk 设备。远端 Domain XML 与 Storage
Volume 是权威数据源；设备移除与 backing 数据删除始终是两个独立操作。

## 首个切片

- 展示已有 file、block、network、volume Disk，不隐藏不支持项。
- 向 persistent VM 挂载同节点已索引且 managed 的 qcow2/raw Storage Volume。
- 支持 virtio、virtio-scsi 与 SATA bus，自动选择未占用 target dev。
- 从 persistent XML 移除选定 Disk 设备，默认保留 Volume 和文件。
- 运行中 VM 首期只修改 persistent config，并明确标记重启后生效。

首个切片不删除 backing 数据、不创建 Volume、不处理 block/network 源写入，也不执行
live attach/detach。CD-ROM/ISO 更换和热插拔作为后续小切片接入同一计划模型。

## 身份与输入

VM 使用 `host_id + Domain UUID`。已有 Disk 设备使用 VM 内唯一 target dev 作为操作
身份，并同时记录 device、bus、source type 与 source identity 防止页面篡改。

新挂载源必须是同 host 的 `ResourceIndex.STORAGE_VOLUME`，身份固定为 Pool UUID +
Volume Key。禁止接收任意文件路径。Volume 必须为 managed、格式 qcow2/raw，且不能
已被当前或其他 VM 引用，除非后续显式支持 shareable。

## XML 修改

1. 权威读取 persistent Domain XML 和 Storage/Domain 索引。
2. 校验页面 VM generation/hash 与 Volume generation/hash。
3. 使用安全 XML 文档定位 `<devices>`，只新增或删除一个 `<disk>`。
4. 新增 Disk 明确生成 driver、source、target；不生成任意 address。
5. 删除按 target dev 定位，并复核 source/device/bus 与页面基线。
6. 保留所有未知元素、属性、注释、设备顺序和其他 Disk。
7. 远端执行 `virt-xml-validate - domain`，展示完整 XML Diff。
8. 确认后重新预检，使用现有 VM 资源锁应用 persistent XML。
9. 写后读取 XML，验证目标设备核心字段；允许 libvirt 生成新设备 PCI address。
10. 从权威 XML 移除新设备后，其余 XML hash 必须等于 original hash。
11. 任何无关变化均失败并恢复 original XML。

## 设备生成规则

- file Volume：`<disk type="file" device="disk">`，source 使用权威 path。
- volume 源：若发现来源由 libvirt Pool/Volume 表达，则保留 pool/name 表达。
- driver：`name="qemu"`，type 来自 Volume format；首期不接受用户自定义 cache/io。
- target：virtio 使用 `vd*`，SATA 使用 `sd*`；virtio-scsi 使用 `sd*` 且要求已有
  virtio-scsi controller，否则拒绝并提示先添加 controller。
- 默认不写 readonly、shareable、serial、WWN、boot order 或 address。

## 计划、恢复与审计

复用 `VmChangePlan`，change type 为 `disk_attach` 或 `disk_detach`。计划保存 VM 与
Volume 基线、目标设备身份、original/proposed XML、Diff、确认摘要和过期时间。

任务不可并发修改同一 VM。配置写入沿用现有 define、写后 hash 接纳和 original XML
回滚。恢复策略为 verify-only：重启后检查 persistent XML 是否匹配 proposed 或
original，不盲目重复 detach。

审计仅记录 Pool UUID、Volume Key 摘要、target dev、bus、format、Task/Operation ID；
不记录媒体 token 或未脱敏 URL。

## 页面

VM 详情增加“磁盘”卡片：

- 每行显示 target、device、source、format、bus、readonly/shareable 和支持状态。
- 挂载表单只列同节点可用 Volume，并显示 Pool、容量、格式和完整 Key。
- 移除按钮进入独立 Diff 页面，明确“只移除设备，保留 backing 数据”。
- 运行中 VM 显示“仅持久配置，重启后生效”警告。
- 技术字段使用等宽字体，375px 使用横向可滚动表格且页面本身不溢出。

## 验证

- 单元：target 分配、重复 target、跨 host Volume、已引用 Volume、未知 XML 保留、
  detach 身份复核、非持久 VM、带外变化、确认过期、写后回滚。
- 页面：CSRF、Diff、危险文案、任务提交、375/1280px、44px 触点。
- 真实节点：运行中 VM config-only 挂载未引用 qcow2；移除后 Volume 仍存在。
- 零残留：清理测试 VM 设备和测试 Volume，不删除既有 VM 或业务磁盘。

## CD-ROM 第二切片

先覆盖节点已有 persistent CD-ROM 设备和节点本地 ISO，建立设备换盘语义：

- 自动展示已有 file/network CD-ROM；不支持写入的类型仍只读展示。
- 首期只操作已有 CD-ROM target，不隐式创建 Controller 或改变 bus/address。
- 本地 ISO 必须来自同节点 managed dir/netfs Pool 的已索引 Volume，文件名和权威
  path 均以 `.iso` 结尾，format 为 raw。
- 挂载只替换目标 CD-ROM 的 file source 并关闭 tray；弹出只移除 source 并打开
  tray，不删除 ISO、Volume 或 CD-ROM 设备。
- VM 和 ISO Volume 的 generation/hash 在预览、确认执行前均复核；挂载期间持有
  VM/Volume 资源锁。ISO 允许被多个 VM 以 readonly CD-ROM 共享。
- 运行中 VM 仍为 config-only，明确提示重启后生效。

平台 `/library` HTTP ISO 不复用当前面向浏览器的 Bearer 下载 URL。libvirt/QEMU
HTTP CD-ROM 支持 source cookies，但任何能力值都会进入 Domain XML；在完成原始
XML、Diff、任务和缓存的凭据脱敏设计前不得把该值写入 VM。平台 ISO 远程挂载作为
下一切片，必须同时解决长期可撤销凭据、QEMU Range、URL/日志脱敏和节点可达性探测。
