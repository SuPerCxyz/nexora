## 1. Inventory and Baseline

- [x] 1.1 Create the route/component/state QA matrix from the real Router and component tree, including compatibility routes and non-applicable controls.
- [x] 1.2 Run an authenticated browser baseline on every reachable page and record overflow, wrapping, overlay, theme and console findings before implementation.

## 2. Design System and Shared Components

- [x] 2.1 Implement persisted Light/Dark theme selection in the application shell with synchronized Ant Design and CSS semantic tokens.
- [x] 2.2 Harden shared App Shell, PageState, StatusTag, Card, Table, Form, code/content and responsive layout rules for text integrity, focus, touch targets and stable sizing.
- [x] 2.3 Harden Drawer, Dropdown, Select popup, Tooltip, Popconfirm and Modal sizing, stacking, scrolling and mobile footer behavior without global overflow hacks.

## 3. Page-Level Corrections

- [x] 3.1 Correct overview, hosts, VMs, storage, media, network, tasks, audit and account list/dashboard pages across desktop, tablet and mobile.
- [x] 3.2 Correct host, VM and task detail pages, including every Tab, action menu, Tooltip, table and safe-to-open confirmation dialog.
- [x] 3.3 Correct onboarding, host-key confirmation, VM creation modes, media copy and VM configuration sections, forms, selects, code blocks and modals.
- [x] 3.4 Correct authentication, loading, empty, error, partial-data, long-text, 404 and UI preview states in both themes.

## 4. Regression and Documentation

- [x] 4.1 Add or update automated tests for theme persistence, accessibility names, responsive structure and content-integrity classes.
- [x] 4.2 Run frontend tests, typecheck, build, React Shell tests and dependency audit; resolve regressions introduced by this change.
- [x] 4.3 Re-run every route at all ten required viewports, Light/Dark desktop and mobile checks, and every safe interactive overlay; record console, network and visual results in the QA matrix.
- [x] 4.4 Reconcile requirements, update project status/roadmap/test status/changelog and complete OpenSpec task state with limitations explicitly recorded.
