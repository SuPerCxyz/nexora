## Context

Nexora 当前由 React 19、TypeScript、Vite 与 Ant Design 6 渲染，同源 History API 负责路由。Design Token 分散在 `static/css/design-tokens.css`、`designTokens.ts`、`theme.ts` 与少量页面 CSS 中；现有基线只有 Light Theme。页面组件约 4.7k 行，功能集中但交互密度高，包含资源列表、详情、创建与高级配置、拓扑图、控制台和危险操作确认。

真实路由清单如下，兼容路由与同组件不同模式也纳入回归：

- 认证：`/initialize`、`/login`
- 总览：`/`
- 节点：`/hosts`、`/hosts/new`、`/hosts/:id/confirm`、`/hosts/:id`、`/manage/hosts/:id`、`/hosts/:id/remove`
- 虚拟机：`/vms`、`/vms/create`、`/vms/create/blank-disk`、`/vms/create/platform-image`、`/hosts/:host/vms/:vm`
- VM 配置：`/hosts/:host/vms/:vm/config`、`/manage/hosts/:host/vms/:vm`、`/manage/hosts/:host/vms/:vm/config`
- 存储与镜像：`/storage`、`/media`、`/media/:id/copy`
- 网络、任务与管理：`/networks`、`/tasks`、`/tasks/:id`、`/audit`、`/settings/account`
- 辅助状态：`/ui-preview`、未知路由 404

重点交互包括应用移动 Drawer、Storage/VM 操作 Dropdown、所有 Select、存储创建 Tabs、VM 详情 Tabs、Collapse 配置段、快照/克隆/迁移/删除/控制台/网络/存储/凭据等 Modal，以及 Tooltip、Popconfirm、Loading/Empty/Error 页面状态。

## Goals / Non-Goals

**Goals:**

- 用一个语义 Token 源统一 Light/Dark、Ant Design 组件与自定义 CSS。
- 建立按页面、视口、主题、状态和交互记录的检查矩阵，修复公共根因后逐页回归。
- 让单行字段、多行内容、技术字段、数值单位、表格、弹层与滚动区域有明确可维护的策略。
- 保留既有业务行为、安全确认流程和页面信息层级。

**Non-Goals:**

- 不新增业务功能、API、数据库字段或远端操作。
- 不重做视觉风格、不引入外部字体/CDN、大型截图框架或新运行时依赖。
- 不在视觉 QA 中提交危险写操作；确认弹层只验证到提交前。
- 本次不部署、不 commit、不 push。

## Decisions

### 1. 主题由应用外壳统一控制

应用外壳持有 `light | dark` 状态，初值优先读取浏览器持久化值，否则使用系统偏好；切换时同步 `data-theme`、`color-scheme` 与 Ant Design ThemeConfig。主题选择保存在本地浏览器，不扩展管理员 API 或数据库。

备选方案是仅使用 `prefers-color-scheme`，但无法满足用户明确切换与持久化；另一个方案是保存到账户设置，会扩大 API 与数据模型范围，故不采用。

### 2. 语义 Token 优先于页面覆盖

Dark Theme 通过一组 CSS 语义变量和 Ant Design dark algorithm 映射实现。页面组件仅声明语义 class，不使用逐页硬编码色值；浮层由 ConfigProvider 统一继承主题。

对于内容布局，建立少量用途明确的公共 class：不可拆分数值/状态、可省略技术字段、可换行描述、稳定标题/操作 Flex、弹层内容滚动和响应式表格。避免全局 `nowrap`、全局 `overflow:hidden` 与像素位移 Hack。

### 3. 检查矩阵分为全量自动巡检和重点人工交互

所有真实路由在 10 个规定视口执行 DOM 级浏览器巡检，记录 Body/关键容器溢出、资源加载和 Console 错误；Light/Dark 至少覆盖每个页面的桌面与移动断点。每个交互类型在其实际页面逐一打开，危险动作停在最终提交之前。

长内容、Empty、Error 与 Loading 通过现有真实数据、API 路由替换和 `/ui-preview` 受控状态组合验证。自动巡检不能替代对定位、换行、层级和视觉密度的实际观察。

### 4. 先修公共组件，再做页面级最小修正

修复顺序为 Theme/Token → App Shell → Card/Table/Form/Overlay 公共规则 → PageState/StatusTag → 页面列配置与容器。只有无法由公共规则正确表达的语义差异才留在页面组件中。

### 5. 验证不引入大型依赖

继续使用 Vitest、TypeScript、Vite、现有 Python React Shell 测试与 `agent-browser`。增加结构和主题测试，但不为一次审计引入 Playwright/Cypress/Storybook；浏览器检查结果记录在 OpenSpec 与 `TEST_STATUS.md`。

## Risks / Trade-offs

- [全量矩阵规模大且动态资源 ID 会变化] → 从当前 API 读取可用 Host/VM/Task/Media ID，清单记录实际进入与不适用项，避免硬编码生产对象。
- [生产数据不能覆盖 Empty/Error/Long Text 全部组合] → 使用同源隔离环境和请求替换构造只读状态，不修改生产业务数据。
- [Dark Token 可能遗漏第三方 Canvas/Terminal] → 为 Cytoscape、xterm/noVNC 容器设置主题语义背景，并逐个打开检查。
- [全局布局规则可能改变特定页面语义] → 每次公共修复后先执行局部组件测试，再运行全路由浏览器巡检。
- [移动表格横向滚动与卡片化存在取舍] → 保留已有移动列表的页面优先卡片化；高密度配置表格保留容器内横向滚动，但禁止 Body 级滚动。

## Migration Plan

1. 先完成只读基线矩阵并记录问题。
2. 落地主题与公共语义规则，运行组件级测试。
3. 修复页面级差异并完成全量浏览器回归。
4. 构建产物通过后才具备后续部署条件；本变更本身不执行部署。
5. 回滚时可按 Theme/App Shell、公共 CSS、页面修复三个层次恢复，不涉及数据迁移。
