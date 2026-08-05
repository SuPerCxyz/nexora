# React + Ant Design 页面与交互设计

## 技术与资产

目标前端使用 React、TypeScript、Vite 和 Ant Design 6。当前路由数量较少，使用
同源 History API 导航；引入 React Router 前必须重新完成依赖安全审计。FastAPI
提供同源内部 Session API 与 HTML 外壳。xterm.js、Cytoscape.js 和 noVNC 本地
打包并封装为 React 组件。Node.js 仅用于构建，运行时不依赖 CDN 或 Node.js 服务。

所有可导航产品页面使用 React 与 Ant Design，包括初始化、登录和复杂 VM 配置。
历史地址返回同一 React Shell；迁移阶段和验收以
`docs/superpowers/specs/2026-07-31-ant-design-frontend-migration-design.md` 为准。

## Design Token

权威 CSS Token 位于 `static/css/design-tokens.css`，Ant Design 映射位于
`frontend/src/app/designTokens.ts` 与 `frontend/src/app/theme.ts`。品牌、成功、
警告、危险、信息、特殊和中性色分别固定为 `#4F8EF7`、`#22C55E`、
`#F59E0B`、`#EF4444`、`#06B6D4`、`#8B5CF6` 和 `#6B7280`。

- Primary：创建、保存、确认、提交和下一步。
- Positive：启动、恢复、启用、连接和挂载。
- Warning：停止、重启、暂停和迁移。
- Info：查看、编辑、快照、克隆、备份、导入和导出。
- Danger：删除、强制操作、卸载和禁用。
- Special：控制台、SSH、日志和维护入口。

使用 B2 视觉基线：紧凑顶部导航、标准舒适密度、浅灰白应用背景、白色内容面和
浅亮无边框圆角状态 Tag。状态 Tag 不显示圆点；表格、卡片和移动列表共享同一状态
映射。禁止渐变、玻璃拟态、霓虹、发光、大面积高饱和背景和非必要阴影。

## 字体

正文使用 Inter、system-ui、Segoe UI、Noto Sans/Noto Sans SC。XML、JSON、Shell、
日志、IP、MAC、UUID、路径、URI、Diff、地址、Token ID 等技术字段使用系统等宽栈。

全局等宽模式开启后，导航、标题、表格、表单、按钮和状态也切换为等宽字体。
不得捆绑未授权商业字体。

## 信息架构

页面包括初始化、登录、总览、节点、VM、创建/高级配置、存储、媒体、宿主网络、
libvirt 网络、任务、审计和设置。

高级配置提供概览、CPU、NUMA、内存、磁盘、控制器、网卡、PCI/USB、固件、
安全设备、控制台、共享目录、原始 XML 和变更历史。

## 状态优先页面

- 首屏优先展示资源状态、关键指标和异常，任务与技术详情降级到次级区域。
- 正常状态使用紧凑状态按钮，不使用重复的健康说明文案。
- 子系统状态占满内容宽度；桌面端每项横向展示图标、名称、配置摘要、状态和入口。
- 窄屏允许子系统项内部换行，但必须保持扫描顺序且不得产生页面级横向滚动。
- 生命周期、控制台和高级配置使用渐进披露，默认不抢占状态信息的视觉层级。

## 结构化代码视图

XML 与 Diff 默认折叠，展开后必须提供缩进、行号、语法着色、复制按钮和代码区滚动。
渲染只能基于转义后的文本节点处理，不得把远端 XML 或 Diff 作为可信 HTML 注入。

## 交互规则

- 危险动作不放在列表主操作区，进入预检/Diff/确认流程。
- 长任务提交后立即返回任务 ID，通过任务中心观察。
- React API 客户端统一处理 Session 过期、CSRF、冲突、验证错误和连接失败。
- 节点和 VM 详情、复杂 VM 配置均由 React 呈现；历史 `/manage/*` 地址继续兼容，
  配置写入仍经过原有预检、Diff、确认、任务和回滚门禁。
- 大列表服务端分页、筛选和排序；列表请求不得触发全量远端扫描。
- 状态同时使用文字/图标，不只依赖颜色。
- 键盘导航、可见焦点和对比度以 WCAG 2.1 AA 为基础目标。
- 浏览器支持范围在首个前端 Spike 后写入 ADR。

## 网络拓扑

Cytoscape.js 展示物理接口、Bond/OVS 只读节点、VLAN、Bridge、Tap/vnet 和 VM NIC。
高亮管理链路、默认路由、管理 IP、断链、无 Carrier 和 MTU 不一致；支持缩放、
自动布局和点击详情，不使用 3D。
