# 资源同步、身份与 XML

## 资源身份

数据库使用独立 opaque ID。原生身份始终位于节点作用域：

- VM：`host_id + domain_uuid`
- libvirt 网络：`host_id + network_uuid`
- Pool：`host_id + pool_uuid`
- Volume：`host_id + pool_uuid + volume_key`
- Snapshot：`host_id + domain_uuid + snapshot_name`
- PCI：`host_id + pci_address`
- USB：`host_id + bus + device + vendor + product`
- 接口：`host_id + ifindex`，名称、MAC 和 PCI 地址作为校验属性

任何内部 API 都必须包含 host 作用域，禁止 `/vms/{uuid}` 形式的全局歧义。

## 自动发现

节点纳管依次验证 SSH、Host Key、sudo 和 libvirt，然后枚举 Domain/XML、快照、
Pool/Volume、libvirt 网络、宿主网络、PCI/USB 和节点设备。首次扫描严格只读。

资源状态包括 `managed`、`read_only`、`partially_supported`、`transient`、
`inaccessible`、`unsupported`、`missing`、`stale`、`changed_out_of_band` 和
`conflict`。不支持的资源不得隐藏。

## 版本与带外变更

每个资源索引保存：

- native identity 和资源类型
- persistent configuration hash
- live configuration hash
- observed generation
- last scanned at
- 能力和支持状态
- 用户标签、备注与来源审计

页面写入携带 base generation/hash。服务端写前重新读取并规范化真实状态；不匹配时
拒绝覆盖，展示 base、current 和 proposed 三方差异。

## XML 安全

- 使用 lxml 安全解析，禁用 DTD、外部实体、网络访问和 XInclude。
- 设置 XML 字节数、深度和节点数量上限。
- 禁止正则、字符串拼接或按表单重建完整 XML。
- 只修改目标节点/属性，保留未知元素、属性、命名空间和顺序语义。
- 原始 XML 编辑同样经过解析、schema/工具校验、Diff 和确认。
- XML 与 Diff 输出进入 HTML 前必须转义。

## 规范化与哈希

persistent XML 与 live XML 分别计算，不得混用。哈希基于安全解析后的规范化表示，
忽略无语义空白和属性表现差异，但不删除未知内容。规范化算法必须版本化；算法升级
触发重新索引，不把全部资源误判为带外修改。

## 修改流程

1. 读取当前 persistent/live XML。
2. 验证 base generation/hash。
3. 解析为保留未知内容的结构。
4. 应用局部结构化变更。
5. 生成并校验 XML。
6. 展示 XML Diff、热修改能力与重启要求。
7. 用户确认后应用。
8. 重新读取并验证最终状态。
9. 写入资源 generation 和审计。

