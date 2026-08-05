# Nexora Design System

本文件是 Nexora 页面视觉和交互的权威实现基线。页面级规则位于 `pages/`，仅可覆盖
局部布局，不能突破 `docs/architecture/FRONTEND.md`。

以下彩色 Token 已由 P6-002 落地到 `static/css/nexora.css`。组件必须继续复用全局
Token，禁止页面各自硬编码颜色或形成第二套视觉体系。

## 产品性格

专业、明亮、鲜活、清晰、可信。信息密度适中，以更有辨识度的品牌蓝、青绿与暖色
强调帮助管理员快速扫描资源和状态。鲜艳色用于操作、图标底板、图表与小面积状态面，
不铺满大面积内容背景。禁止营销落地页式超大标题、玻璃拟态、霓虹和无意义动效。

## 技术体系

- Tabler UI 与 Tabler Icons，禁止混用其他图标库。
- Jinja2 + HTMX + 少量原生 JavaScript，不使用 SPA。
- 静态资源本地打包，不使用 CDN 或远程字体。

## 颜色

| Token | Value | Purpose |
|---|---|---|
| `--nx-bg` | `#F8FAFC` | 页面背景 |
| `--nx-surface` | `#FFFFFF` | 卡片和表单 |
| `--nx-text` | `#0F172A` | 主文本 |
| `--nx-muted` | `#64748B` | 次级文本 |
| `--nx-border` | `#E2E8F0` | 边框 |
| `--nx-primary` | `#2563EB` | 主操作与焦点 |
| `--nx-primary-hover` | `#1D4ED8` | 主操作 hover |
| `--nx-secondary` | `#0891B2` | 信息与基础设施强调 |
| `--nx-accent` | `#EA580C` | 关键 CTA 与注意力强调 |
| `--nx-success` | `#059669` | 成功 |
| `--nx-warning` | `#D97706` | 警告 |
| `--nx-danger` | `#DC2626` | 危险 |

文本与背景达到 WCAG 2.1 AA；状态必须同时包含文字或图标，不能只用颜色。卡片可用
5%–10% 的蓝、青、紫、绿、橙 tint 区分类型，正文承载面仍保持白色或近白色。

## 字体

- 正文：Inter、system-ui、Segoe UI、Noto Sans、Noto Sans SC、sans-serif。
- 技术内容：ui-monospace、SFMono-Regular、Cascadia Code、JetBrains Mono、
  Menlo、Monaco、Consolas、Liberation Mono、Noto Sans Mono、monospace。
- 正文最小 14px，表单输入 16px，默认行高至少 1.5。
- 全局等宽模式通过根元素 class 切换，不改技术字段语义标记。

## 间距与形状

- 间距阶梯：4、8、12、16、24、32、48px。
- 卡片圆角 10px，按钮和输入框 8px。
- 卡片使用 1px 边框和最多 `0 8px 24px rgba(37,99,235,.08)` 阴影。
- 认证页内容宽度不超过 420px；管理页面使用响应式容器。

## 表单与交互

- 每个字段有持久可见 label；placeholder 不代替 label。
- 错误紧邻字段显示，并用 `aria-describedby` 关联。
- 主要触控目标至少 44×44px，相关控件间距至少 8px。
- 键盘焦点清晰，禁止移除 outline 后不提供替代。
- hover/focus 过渡 150–200ms；遵循 `prefers-reduced-motion`。
- 提交期间禁用重复提交并提供文字反馈。
- 危险操作不放在默认主按钮位置。

## 页面规则

- 初始化页只解释首次管理员创建，不展示未配置的管理导航。
- 登录页不泄露用户名是否存在，错误信息保持统一。
- 页面必须在 375、768、1024、1440px 宽度下无横向滚动。
- 无 JavaScript 时认证主流程仍可使用。

## 交付检查

- Tabler Icons 具有可访问名称，装饰图标使用 `aria-hidden=true`。
- 键盘可完成全部操作，焦点顺序符合视觉顺序。
- 验证错误、Session 过期、CSRF 失败和服务错误均有明确反馈。
- 不记录或回显密码、Session、CSRF 或完整敏感 Token。
