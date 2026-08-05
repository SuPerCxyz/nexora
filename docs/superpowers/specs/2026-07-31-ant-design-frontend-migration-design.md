# React + Ant Design 前端迁移设计

## 目标

将 Nexora 的 Tabler/Jinja2/HTMX 页面分阶段迁移为 React、TypeScript 与
Ant Design 6，最终形成统一的现代运维工作台。迁移保持 FastAPI、SQLite、远端
操作、安全确认、任务状态机和现有 URL 语义不变。

## 已确认视觉方向

- 使用紧凑顶部导航，不采用侧边栏或混合导航。
- 使用 Ant Design 标准舒适密度，避免过度压缩表格和表单。
- 默认浅色主题，内容背景近白，主色使用 Ant Design 品牌蓝。
- 状态 Tag 使用浅亮实色背景、深色文字、无边框，并同时保留文字和状态点。
- 状态文案面向管理员显示中文，不直接展示内部英文枚举。
- 页面保持状态优先，任务与技术详情不抢占首屏层级。

## 目标架构

- 新增 `frontend/`，使用 React、TypeScript、Vite、Ant Design 6 和 React Router。
- FastAPI 继续负责 Session、CSRF、业务数据、任务、审计和远端操作。
- React 只调用同源 `/internal/*` JSON API，不新增公共 API、Token 或 RBAC。
- Vite 构建产物复制到 Python 运行镜像，运行时不包含 Node.js 服务。
- 保持单容器、单 Uvicorn worker、SQLite 和现有非 privileged 运行边界。
- React 与 Jinja2 在迁移期可并存，但同一 URL 只允许一种前端负责。
- URL、刷新和深链接保持稳定；FastAPI 对已迁移页面返回 React HTML 外壳。
- xterm、noVNC、Cytoscape 和代码视图封装为 React 组件继续使用。

## 数据流与安全

- `/internal/session` 返回管理员偏好、CSRF 状态和可用功能信息。
- 所有写请求使用同源 Session Cookie，并携带 `X-CSRF-Token`。
- API 错误统一为 `code`、`message`、`field_errors`、`conflict` 和 `task_id`。
- 远端状态、Diff、确认 Token、资源锁和危险操作门禁继续由后端权威实现。
- React 不把凭据、确认 Token、XML 或敏感任务输出写入 `localStorage`。
- Session 过期进入登录页；冲突、带外变更和恢复使用统一 Result 页面。
- CSP 继续禁止 CDN 与不受控内联脚本，所有资源在构建阶段本地打包。

## 迁移阶段

1. 基础平台：Vite、Ant Design、路由、Session/CSRF 客户端、错误页和 Design Token。
2. 核心只读页面：顶部导航、总览、节点列表、虚拟机列表、分页和筛选。
3. 资源详情：节点、VM、指标、Guest Agent、XML、快照和设备信息。
4. 创建与变更：节点接入、VM 创建、CPU/内存/磁盘、媒体、存储和网络写入。
5. 运维页面：任务、审计、设置、串口、VNC 和网络拓扑。
6. 收敛清理：主路由完成 React 接管并清理重复视觉定义；按最终产品边界保留认证与
   `/manage/*` 复杂配置兼容岛，完成最终兼容验证。

每阶段必须可独立部署和回滚，保留上一镜像及数据库备份。不得在一个页面内混用
React 与 Jinja2 组件，也不得在迁移过程中改变后端操作语义。

## 组件与交互规范

- 顶部导航使用 Ant Design Menu，移动端收敛为可访问的抽屉导航。
- 列表使用 Table，服务端分页、筛选和排序，不触发隐式远端扫描。
- 表单使用 Form，但后端仍执行全部安全校验；前端校验只改善反馈速度。
- 危险动作使用预检、Diff、确认和 Result 流程，不以普通 Modal 直接执行。
- 状态、告警和资源类型分别使用 Tag、Alert 和 Typography，不混淆语义。
- XML/Diff 保持默认折叠、格式化、行号、着色、复制和独立滚动区域。
- 技术 ID、路径和 Hash 使用 Typography.Text 等宽、可复制和安全换行。

## 测试与验收

- Vitest 与 React Testing Library 覆盖组件、路由、表单和错误状态。
- FastAPI 测试覆盖 `/internal/*` 的认证、CSRF、分页、校验和错误契约。
- Browser QA 覆盖 375、768、1280、1440px、键盘、刷新和深链接。
- 每阶段运行 Python 测试、TypeScript 检查、前端测试、构建和容器健康检查。
- 状态 Tag 必须为 B2 浅亮无边框样式，不得出现原始英文状态文案。
- 最终镜像不得包含 Node.js，容器保持 UID 10001、非 privileged、0 devices。

## 风险与控制

- 55 个模板、41 个表单和 23 个页面路由决定了迁移必须分阶段执行。
- 过渡期双前端可能造成样式和错误语义分裂，共享契约必须先于页面迁移建立。
- Jinja 表单改为 JSON 后不能弱化 CSRF、确认 Token、字段校验或审计信息。
- 控制台和拓扑具有独立生命周期，必须在普通 CRUD 页面稳定后再迁移。
- 删除兼容岛中的 Tabler/HTMX 前，必须证明认证、复杂配置和恢复入口已有 React
  等价实现；在此之前不得为追求依赖清理削弱安全预检、Diff 或回滚能力。
