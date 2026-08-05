# React 零旧前端与 VM 操作闭环设计

## 目标

所有可导航页面、预检、Diff、确认和错误反馈由 React/Ant Design 与同源
`/internal/*` JSON API 承载。Jinja 仅保留 `react_shell.html`，不得再作为业务响应，
React 也不得解析 HTML 获取计划字段。

同时补齐节点优先的 VM 创建、空白磁盘、快照、克隆、关机迁移、删除、重命名、
网卡和自动启动操作。

## 边界

- 保留 FastAPI、SQLite、Session、CSRF、任务和 RemoteExecutor 安全架构。
- 保留 `host_id + native_id` 资源身份和远端真实状态权威原则。
- 不实现 external/live snapshot、在线迁移和 direct/macvtap 写入。
- aarch64 与 Rocky 之外 RHEL 系发行版验证继续暂缓。
- 不引入多用户、RBAC、公共 API、Redis、Celery 或额外运行服务。

## 前端收敛

- 所有旧表单预检转换为 JSON 请求与 JSON 预览响应。
- 统一预览契约包含计划 ID、确认 Token、操作类型、摘要、Diff 和风险提示。
- 统一应用契约返回任务 ID 与任务详情地址。
- 旧 GET 地址返回 React Shell 或显式重定向到对应 React 地址。
- 删除业务 Jinja 渲染、模板和 React `DOMParser` 兼容层。
- 自动化测试阻止新增非 Shell `TemplateResponse`。

## VM 创建

创建页首先选择节点，再选择系统盘来源：空白磁盘、现有 Volume 或平台镜像。
空白磁盘模式选择同节点可写 Pool、容量和 qcow2/raw 格式。网络、ISO、CPU、内存、
UEFI、Secure Boot、TPM 和 Driver ISO 继续使用现有能力校验。

空白磁盘与 VM 定义由同一持久化任务执行。任务记录是否由本次操作创建 Volume；
失败时只清理本次 partial/新 Volume，绝不删除已有 Volume。

## VM 操作

- 快照：React 提供创建、leaf 删除和 current 恢复，沿用现有 internal qcow2 边界。
- 克隆：React 提供同节点和跨节点完整克隆；关机迁移在克隆验证后显式清理源端。
- 删除：仅关机 VM；默认只 undefine，磁盘和 NVRAM 必须逐项勾选并输入 VM 名称。
- 重命名：仅关机 persistent VM，保持 UUID 和磁盘不变，写后重新发现并验证。
- 自动启动：启用和禁用均进入任务队列并执行权威复核。

## 网卡操作

支持新增、删除、修改 MAC、切换同节点 Bridge/libvirt Network。MAC 必须合法且在
同节点 VM 范围内唯一。关机 VM 修改 persistent XML；运行中 VM 仅在 live/config
双路径均可预检、验证和回滚时允许，否则返回明确的关机要求。

## 存储闭环

Pool 创建、生命周期、删除以及 Volume 创建、扩容、删除全部进入 internal JSON API。
删除前继续扫描 VM 引用，默认保留底层文件或 export；数据删除必须单独确认。

## 安全与恢复

所有写操作执行资源版本比较、XML 安全解析、结构化修改、Diff、确认 Token、锁、
任务步骤、执行前重验和写后权威验证。SQLite 事务不跨 SSH。可恢复任务必须区分
未执行、已执行待验证和需要人工处理状态。

## 验收

- 除 `react_shell.html` 外没有业务模板渲染。
- React 不使用 `DOMParser` 或抓取 HTML 表单。
- 七项功能均有成功、冲突、失败和恢复测试。
- 375/768/1280/1440px 无横向溢出和控制台/CSP 错误。
- Rocky 隔离资源完成创建、网卡、快照、克隆、重命名、自动启动和删除闭环。
- 全量 Python/React 静态检查、测试、构建和依赖审计通过后才部署。
