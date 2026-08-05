# XML 保留与安全解析 Spike

## 目标

验证 Nexora 能在不重建 Domain XML 的前提下执行结构化 CPU 修改，并为带外变更提供
稳定、版本化的配置 hash 和可审阅 Diff。

## 决定

- 使用 `lxml 6.x`，唯一解析入口为 `LibvirtXmlDocument.parse()`。
- parser 固定关闭实体解析、DTD 加载、网络、恢复模式和 `huge_tree`。
- 任何包含 DOCTYPE 的文档直接拒绝；XInclude 节点只保留，不调用展开。
- 默认单份 XML 上限 10 MiB、深度 128、元素节点 100,000。
- 原树保留注释、PI、CDATA、命名空间、未知元素/属性和子节点顺序。
- 结构化修改只定位并更新目标元素/属性，不通过表单模型重建 Domain。

## Hash

算法标识为 `nexora-libvirt-c14n2-v1`。计算前复制原树，只移除未处于
`xml:space="preserve"` 范围内的元素间缩进空白，再执行带注释 C14N2 和 SHA-256。

算法版本必须与 digest 一起持久化。升级算法时重新建立索引，不把版本变化当作带外
修改。persistent 与 live XML 分别计算，调用方不得混用。

## CPU 修改

`CpuTopologyChange` 校验所有值为正数、current 不超过 maximum，且：

`sockets × dies × clusters × cores × threads = maximum_vcpus`

更新仅涉及 `vcpu` 文本/current 和 `cpu/topology` 的标准维度属性。已有 placement、
mode、model、feature、NUMA、vendor 扩展和设备内容保持不变。

## 验证边界

本 Spike 证明本地解析、保留、Diff 和 topology 校验，不替代远端 libvirt schema
验证。写操作后续仍必须通过 RemoteExecutor 把 proposed XML 传给
`virt-xml-validate` 或等价 libvirt 校验，再执行确认和最终状态回读。

## 自动化证据

`tests/xml/` 覆盖外部实体、DOCTYPE、XInclude、资源上限、错误根节点、空白和属性
顺序等价、未知内容 hash、`xml:space`、Diff、CPU 合法性及未知扩展保留。
