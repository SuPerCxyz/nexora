# Tabler 页面与交互设计

## 技术与资产

使用 Jinja2、HTMX、Tabler UI、Tabler Icons 和少量原生 JavaScript。Alpine.js
仅用于必要局部状态。CodeMirror、xterm.js、Cytoscape.js 和 noVNC 本地打包。
不使用 SPA，不在运行时依赖 CDN 或 Node.js 服务。

## Design Token

- 页面背景：`#F6F8FA`
- 卡片背景：`#FFFFFF`
- 主文本：`#1F2937`
- 次级文本：`#667085`
- 边框：`#E4E7EC`
- 强调色：柔和蓝或蓝绿色
- 状态色：低饱和绿、橙、红

使用适度留白、细边框、小圆角和轻阴影；禁止霓虹、大面积渐变、重阴影和过度动画。

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

## 交互规则

- 危险动作不放在列表主操作区，进入预检/Diff/确认流程。
- 长任务提交后立即返回任务 ID，通过任务中心观察。
- HTMX 统一处理 Session 过期、CSRF、冲突、验证错误和连接失败。
- 大列表服务端分页、筛选和排序；列表请求不得触发全量远端扫描。
- 状态同时使用文字/图标，不只依赖颜色。
- 键盘导航、可见焦点和对比度以 WCAG 2.1 AA 为基础目标。
- 浏览器支持范围在首个前端 Spike 后写入 ADR。

## 网络拓扑

Cytoscape.js 展示物理接口、Bond/OVS 只读节点、VLAN、Bridge、Tap/vnet 和 VM NIC。
高亮管理链路、默认路由、管理 IP、断链、无 Carrier 和 MTU 不一致；支持缩放、
自动布局和点击详情，不使用 3D。

