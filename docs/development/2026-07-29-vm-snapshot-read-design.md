# VM 快照只读纵向切片设计

## 目标

在 VM 详情页展示节点上已存在的 libvirt Snapshot，不要求重新导入或添加 Nexora
标签。远端 libvirt 状态继续是权威数据源。

## 首期边界

- 按 `host_id + domain_uuid + snapshot_name` 识别。
- 展示名称、状态、创建时间、内存模式、磁盘模式、资源状态与原始 Snapshot XML。
- `managed`、`read_only`、`partially_supported`、`missing` 和冲突状态均不隐藏。
- VM 详情读取仅查询 SQLite 最近一次完整扫描，不触发远端扫描。
- 原始 XML 使用技术等宽字体并进行 HTML 转义。
- 每台 VM 最多返回 2,000 个 Snapshot，超过限制时由后续分页任务处理。

## 暂不写入

创建、删除和恢复 Snapshot 需要独立持久化确认计划。该计划会引入数据库 schema，
必须在开始写操作前获得明确迁移授权。只读切片不复用 VM XML 计划来规避迁移，
避免错误的恢复语义。

## 验证

- 单元测试节点与 Domain 作用域、排序、数量限制和 XML 关联。
- Web 测试已有 Snapshot 无需导入即可展示，XML 不执行 HTML。
- Browser QA 覆盖 1280px 与 375px，无横向页面溢出和控制台错误。
