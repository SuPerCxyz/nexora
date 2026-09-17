# Frontend Visual QA Matrix

本矩阵从 `frontend/src/app/App.tsx`、`src/nexora/web/frontend.py` 与页面组件实际引用生成。`Pending` 表示尚未执行浏览器回归；危险动作只打开到最终提交前，不触发业务写入。

## Viewport / Theme / State Matrix

| 维度 | 覆盖值 |
|---|---|
| Viewport | 1920×1080、1600×900、1440×900、1366×768、1280×800、1024×768、768×1024、430×932、390×844、360×800 |
| Theme | Light、Dark |
| State | Normal、Loading、Empty、Error、Partial Data、Large Data、Long Text、Small Screen |
| Interaction | Default、Hover、Focus-visible、Active、Selected、Disabled、Loading、Open、Viewport Edge |

## Route Matrix

| 页面 | 路由 | 真实组件 / 模式 | 必查组件与状态 | 基线 | 修复后 |
|---|---|---|---|---|---|
| 初始化 | `/initialize` | `AuthPage(initialization)` | Card、Form、Input、Password、Alert、提交按钮 | Pending | Pending |
| 登录 | `/login` | `AuthPage(login)` | Logo、Card、Form、Input、Password、错误态、提交按钮 | Pending | Pending |
| 总览 | `/` | `OverviewPage` | Metric Card、状态分布、子系统列表、Loading/Error | Pending | Pending |
| 节点列表 | `/hosts` | `HostsPage` | Header Action、Table、移动 Card、Pagination、Empty/Error | Pending | Pending |
| 节点接入 | `/hosts/new` | `HostOnboardingPage` | Steps、2 Select、Form、Password、Alert、按钮状态 | Pending | Pending |
| Host Key 确认 | `/hosts/:id/confirm` | `HostKeyConfirmationPage` | Steps、Descriptions、Fingerprint、Checkbox、Spin/Error | Pending | Pending |
| 节点详情 | `/hosts/:id` | `HostDetailPage` | Header、Fact Cards、Descriptions、5 Cards、2 Tables、长技术字段 | Pending | Pending |
| 节点详情兼容 | `/manage/hosts/:id`、`/hosts/:id/remove` | `HostDetailPage` | 与节点详情一致；移除 Modal 入口 | Pending | Pending |
| VM 列表 | `/vms` | `VmsPage` | 2 Select、Table、移动 Card、Pagination、Status/Restart Tag | Pending | Pending |
| VM 创建 | `/vms/create` | `VmCreatePage(existing)` | Steps、来源 Radio、全部 Select/Form、预览、Loading/Error | Pending | Pending |
| VM 空盘创建 | `/vms/create/blank-disk` | `VmCreatePage(blank)` | Pool/格式/容量、长路径与选项、预览 | Pending | Pending |
| VM 镜像创建 | `/vms/create/platform-image` | `VmCreatePage(media)` | Media/Pool/Cloud-init/网络模式、长选项、预览 | Pending | Pending |
| VM 详情 | `/hosts/:host/vms/:vm` | `VmDetailPage` | Action Bar、危险 Dropdown、3 Tabs、Tables、Tooltips、Modals | Pending | Pending |
| VM 配置 | `/hosts/:host/vms/:vm/config` | `VmConfigurationPage` | 5 Collapse Sections、Forms、Tables、历史/设备/卷 Modal、Popconfirm | Pending | Pending |
| VM 配置兼容 | `/manage/hosts/:host/vms/:vm`、`/manage/hosts/:host/vms/:vm/config` | `VmConfigurationPage` | 与 VM 配置一致 | Pending | Pending |
| 存储 | `/storage` | `StoragePage` | 节点 Select、2 Tabs、Forms、2 Tables、2 Dropdown、预览 Modal | Pending | Pending |
| 镜像 | `/media` | `MediaPage` | Header Action、Table、移动 Card、凭据 Modal、Empty/Error | Pending | Pending |
| 镜像复制 | `/media/:id/copy` | `MediaCopyPage` | Form、长选项 Select、Alert、按钮状态 | Pending | Pending |
| 网络 | `/networks` | `NetworkPage` | Host Select、Fact Cards、2 Tooltip、Topology、2 Tables、2 Create Modal | Pending | Pending |
| 任务列表 | `/tasks` | `TasksPage` | 2 Select、Table、状态/进度、Empty/Error | Pending | Pending |
| 任务详情 | `/tasks/:id` | `TaskDetailPage` | Progress、步骤 Table、Alert、审计输出/长错误/代码滚动 | Pending | Pending |
| 审计 | `/audit` | `AuditPage` | 2 Select、Table、Pagination、长命令与输出 | Pending | Pending |
| 设置 | `/settings/account` | `AccountPage` | 2 Cards、Form、Language Select、InputNumber、登录历史 Table | Pending | Pending |
| UI 状态预览 | `/ui-preview` | `PreviewPage` | Tokens、Card、长短内容、Loading/Empty/Error 组合 | Pending | Pending |
| 404 | 未知路由 | `Result(404)` | Result、返回按钮、移动/主题 | Pending | Pending |

## Interactive Component Matrix

| 类型 | 实际位置 | 检查项 | 基线 | 修复后 |
|---|---|---|---|---|
| Drawer | App 移动主导航 | 360/390/430px、焦点、遮罩、Esc、滚动、Theme | Pending | Pending |
| Dropdown | VM 危险操作、Pool 操作、Volume 操作 | 首/末行、长文案、disabled、视口边缘、z-index | Pending | Pending |
| Select / Combobox | 设置、接入、VM/任务/审计筛选、存储、网络、创建与配置表单 | Trigger 省略、长 Option、搜索、clear、disabled、移动 Popup | Pending | Pending |
| Tabs | 存储池/卷；VM 设备/快照/XML | 标签单行、计数、切换、横向滚动、内容高度 | Pending | Pending |
| Collapse | VM 配置 5 Section | Header/状态/按钮对齐、长表单、移动展开 | Pending | Pending |
| Modal / Dialog | 节点移除、存储预览、网络创建、媒体凭据、VM 控制台/动作/克隆/迁移/删除/快照、配置历史、网卡更新、卷创建 | Max height、内部滚动、Header/Footer、长标题、Esc、焦点返回、移动宽度 | Pending | Pending |
| Popconfirm | VM 生命周期、配置历史回滚 | 定位、长描述、按钮单行、Theme、键盘 | Pending | Pending |
| Tooltip | StatusTag、网络指标/状态、不可挂载卷 | Ellipsis 完整值、边缘翻转、宽度、Theme | Pending | Pending |
| Table | 资源列表、详情、配置、审计、任务 | Header/Cell 单行策略、技术字段、单位、Empty/Loading、容器滚动 | Pending | Pending |
| Code / XML / Log | VM XML、配置 Diff、任务输出、审计输出、控制台 | 横向/纵向滚动、`pre` 结构、复制入口、Theme、max-height | Pending | Pending |
| Graph / Console | 网络拓扑、Serial、VNC | 容器尺寸、resize、Theme、无裁剪、全屏/移动 | Pending | Pending |

## Baseline Findings

基线日期：2026-08-13。生产只读版本 `http://127.0.0.1:8002`，已认证实际渲染；主路由分别检查 1440×900 与 390×844。全部已进入页面均无 Body 级横向滚动、图片加载失败或浏览器页面错误。证据位于 `/tmp/nexora-visual-qa-baseline/screenshots/`。

| ID | 严重度 | 页面 / 状态 | 可复现问题 | 证据 | 处理状态 |
|---|---|---|---|---|---|
| VQA-001 | P0 | 镜像 `/media`，390×844 | 桌面表格直接出现在移动端，操作列及“创建虚拟机”入口被 Card 右侧裁剪；虽然 Body 不滚动，但重要操作不可见且横向滚动提示不足 | `baseline-media-mobile.png` | Resolved |
| VQA-002 | P1 | 节点详情，390×844 | 节点 UUID 在 Fact Card 中按连字符断成两行；此类技术标识应单行省略并可查看完整值 | `baseline-host-detail-mobile.png` | Resolved |
| VQA-003 | P0 | VM 配置兼容路由 `/manage/hosts/:host/vms/:vm/config` | 客户端 Router 明确识别该地址，但服务端未返回 React Shell，直接得到 JSON 404，页面视觉与产品完全脱离 | `baseline-missing-compat-route.png` | Resolved |
| VQA-004 | P1 | 全站 | 现有生产版本只有 Light Theme，无法执行 Dark 逐页验收 | 浏览器与 ThemeConfig 基线 | Resolved |

补充观察：存储页移动表格的操作列位于其内部横向滚动区域；该页面在后续修复中保留高密度表格内部滚动，但必须增加稳定宽度、边缘可达性与不裁剪验证。`/initialize` 在已初始化环境按产品规则重定向到 `/login`；初始化表单将在隔离状态预览中验证。未知 URL 由服务端直接返回 404，客户端 `Result` 状态将在 `/ui-preview` 受控组合中验证。

## 修复后回归（2026-08-13）

- 以生产 SQLite 的一次性只读快照启动隔离实例，显式禁用 Task Coordinator 与 Metrics Sampler；未连接或修改远端资源，结束后清除快照、Cookie 与浏览器 Profile。
- 25 条实际路由（含真实 Host、VM、Task、Media 详情及 `/manage/*` 兼容地址）在 10 个规定视口执行 Light 顶层导航，共 250 次；1440×900 与 390×844 再执行 Dark，共 50 次。最终 Body overflow、破图、React Shell 缺失与原始 JSON 404 均为 0。
- `/media` 使用 6 条真实数据在 430×932、390×844、360×800 的 Light/Dark 复验：移动 Card 数 6、桌面表格不可见、Body overflow 0；SHA/路径单行省略、状态与全部 Action 完整可达。
- 实际打开并测量移动 Drawer、长内容 Modal、Network Modal、Select popup、VM 强制操作 Dropdown、Storage 操作 Dropdown；均完整位于 390×844 视口。Modal Footer 可见，Escape 可关闭。
- 实际进入 VM 的设备/快照/XML 三个 Tab、Storage 的存储池/存储卷两个 Tab与 VM 配置五个 Collapse Section；配置页 Body overflow 0。
- `/ui-preview` 覆盖 Long Text、技术字段、数值单位、Partial Data、Loading、Empty、Error、404 与长内容 Modal；初始化表单在全新隔离实例实际渲染并检查。
- 浏览器 Page Errors 与 Console 均为空。截图：`/tmp/nexora-visual-regression-media-mobile-dark-fixed.png`、`/tmp/nexora-visual-regression-modal-mobile-dark.png`、`/tmp/nexora-visual-regression-preview-mobile-dark.png`。
