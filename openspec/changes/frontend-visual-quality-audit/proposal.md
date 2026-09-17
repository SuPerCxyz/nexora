## Why

Nexora 已具备完整的 React/Ant Design 页面体系，但现有视觉验证主要集中在主路由和少量断点，尚未形成覆盖所有详情页、Tab、弹层、长内容、异常状态与主题的统一浏览器验收闭环。需要从 Design System 根因出发完成一次全量视觉 QA，消除内容裁剪、异常换行、弹层越界和响应式不一致，并让结果可持续回归。

## What Changes

- 从真实 Router、导航与页面组件建立完整页面、Tab、表格、表单和弹层清单及检查矩阵。
- 统一文本、技术字段、数字单位、Flex/Grid、表格、Card、表单、Dropdown、Tooltip、Modal、Drawer 和代码区域的内容完整性规则。
- 补齐可切换并持久化的 Light/Dark Theme，统一 Ant Design Token 与 CSS 语义 Token，不改变页面信息架构或业务流程。
- 修复桌面、平板和移动端的溢出、裁剪、异常换行、触控目标、焦点可见性和弹层可操作性问题。
- 使用真实浏览器逐页、逐 Tab、逐弹层回归，并增加适合当前仓库的自动化视觉结构断言；不引入大型视觉测试依赖。

## Capabilities

### New Capabilities

- `frontend-visual-quality`: 定义全站页面与交互容器在主题、响应式、长短内容、加载/空/错状态下的视觉一致性和可访问性要求。

### Modified Capabilities

无。

## Impact

- 主要影响 `frontend/src/app/` 的应用外壳、主题映射、公共样式和页面组件，以及相应前端测试。
- 必要时更新现有前端架构、项目状态、路线图、测试状态和变更日志文档。
- 不改变内部 API、业务数据库、远端执行、安全确认流程、产品信息架构或运行时依赖；不包含部署、提交或远程 Git 操作。
