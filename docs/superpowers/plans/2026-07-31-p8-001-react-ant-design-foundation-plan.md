# P8-001 React + Ant Design 基础平台实施计划

## 目标与边界

建立 React、TypeScript、Vite、Ant Design 6 的可测试构建与运行基础，并提供认证后的
内部 Session API。阶段内只增加未导航公开的 `/ui-preview` 暂存入口，不接管现有
Jinja2 业务 URL，不改变数据库、任务、远端操作或危险操作语义。

## 实施步骤

### 1. 固化内部 API 契约测试

- 新增 `tests/web/test_internal_session_api.py`。
- 先覆盖未登录 `401`、已登录 Session 偏好、CSRF 返回、无缓存头和错误结构。
- 新增 `src/nexora/web/internal/contracts.py`，定义 Session 与错误响应模型。
- 验证：`uv run pytest -q tests/web/test_internal_session_api.py`。

### 2. 建立内部 Session API

- 新增 `src/nexora/web/internal/auth.py`，集中解析 Session 与验证 `X-CSRF-Token`。
- 新增 `src/nexora/web/internal/session.py`，实现 `GET /internal/session`。
- 新增 `src/nexora/web/internal/router.py`，统一 `/internal` 路由边界。
- 修改 `src/nexora/app.py` 注册内部路由，不开启 OpenAPI。
- CSRF 明文只通过已认证同源响应返回，不写入浏览器持久化。

### 3. 为 Ant Design 增加 CSP nonce

- 修改 `src/nexora/web/middleware.py`，每请求生成 nonce 并写入 CSP。
- `script-src` 保持仅 self/nonce；`style-src-elem` 允许 self/nonce；
  `style-src-attr` 仅为 Ant Design 运行样式允许 inline 属性。
- React Shell 将 nonce 传入启动配置，Ant Design `ConfigProvider` 的 CSP 配置使用
  同一 nonce，确保 CSS-in-JS style 标签通过策略校验。
- 新增 `tests/web/test_frontend_security.py`，覆盖 nonce 唯一性、Header 与 Shell 一致性。
- 禁止加入全局 `script-src 'unsafe-inline'` 或 CDN 域名。

### 4. 创建独立前端工程

- 新增 `frontend/package.json`、`frontend/package-lock.json`、`tsconfig*.json`、
  `vite.config.ts`、`vitest.config.ts` 和 `src/` 入口。
- 固定 React、React DOM、Ant Design 6、Ant Design Icons、Vite、
  TypeScript、Vitest 与 React Testing Library 版本。
- 2026-07-31 npm audit 显示 React Router 当前可用版本均有 high 漏洞；P8-001
  单入口不引入该依赖，P8-002 接管业务 URL 前重新审计并选择已修复版本。
- 增加 `typecheck`、`test`、`build` 脚本；不加入运行时 Node 服务。

### 5. 建立 API 客户端与 Session 启动流程

- 新增 `frontend/src/api/client.ts`、`contracts.ts`、`session.ts`。
- 默认 `credentials: same-origin`，写请求自动附加内存中的 CSRF Header。
- 统一处理 `401`、`403`、`409`、字段错误和任务响应；不得使用 `localStorage`。
- 新增对应 Vitest，模拟 Session 成功、过期、冲突和非法响应。

### 6. 实现 B2 Ant Design 应用外壳

- 新增 `frontend/src/app/App.tsx`、路由、顶部导航、移动 Drawer、错误边界与加载态。
- 应用启动读取 Shell 中的一次性 nonce，只在内存中传给 Ant Design `ConfigProvider`。
- 新增 `theme.ts` 和全局 CSS：顶部导航、标准舒适密度、`#1677ff` 主色、
  浅亮无边框状态 Tag、44px 触控目标和技术字段等宽规则。
- `/ui-preview` 只展示平台状态与迁移说明，不链接到主导航。
- 组件测试覆盖导航选中、移动 Drawer、中文状态文案和键盘焦点。

### 7. 提供 React Shell 与 Vite manifest 加载

- 新增 `templates/react_shell.html` 与 `src/nexora/web/frontend.py`。
- 新增认证路由 `/ui-preview` 与 `/ui-preview/{path:path}`，刷新时返回同一 Shell。
- 从构建 manifest 解析带 hash 的 JS/CSS，不硬编码文件名；缺失资产时 fail closed。
- Shell 只包含外部资源标签、nonce meta 和 React mount point，不嵌入敏感数据。

### 8. 集成本地构建与容器镜像

- 修改 `Dockerfile`：独立构建 legacy assets 与 `frontend/`，复制 dist 到
  `/app/static/app`，运行阶段不复制 Node/npm。
- 保留根 `package.json` 与 `scripts/build-assets.mjs`，直到 P8-006 清理 Tabler/HTMX。
- 更新 `.dockerignore`、README 构建命令和开发说明，不引入开发服务器到生产路径。

### 9. 完成阶段验证与部署

- 前端：`npm --prefix frontend ci`、`typecheck`、`test -- --run`、`build`。
- 后端：定向 API/CSP 测试，再运行 Ruff、Mypy 与 `uv run pytest -q`。
- Browser QA：`/ui-preview` 覆盖 375/768/1280/1440px、刷新、深链接、Session 过期、
  无横向溢出、无控制台错误；确认旧 Jinja 页面行为不变。
- 镜像：构建后验证 healthy、UID 10001、非 privileged、0 devices、无 Node/npm。
- 部署前创建一致备份并保留旧镜像；验证通过后更新 P8-001 为 DONE、P8-002 为
  ANALYZING，并同步 `PROJECT_STATUS.md`、`ROADMAP.md`、`TEST_STATUS.md`、CHANGELOG。

## 完成标准

`/ui-preview` 可在正式单容器内安全加载 B2 Ant Design 外壳，内部 Session API 与
CSP nonce 有自动化证据，现有页面无回归，且运行镜像不含 Node.js。P8-002 才开始
让 React 接管 `/`、`/hosts` 和 `/vms`。
