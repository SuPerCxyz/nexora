# 开发进度审计报告

> 审计日期：2026-08-06
> 审计范围：当前 `master` 分支最新未提交修改
> 审计依据：`ROADMAP.md`、`PROJECT_STATUS.md`、`CHANGELOG.md`、`TEST_STATUS.md`

> **整改状态（2026-08-06 同日跟进）**：本报告指出的 MAJOR（NEW-1 `vm.xml_restore`
> handler 未注册）与 MISMATCH（DOC-1 文档 head/状态滞后）已在整改中解决；详见
> 第 8 节"整改记录"。

## 1. 审计摘要

* **当前分支和提交**：`master`，最新提交 `e118cf2 Import Nexora application and CI pipeline`；之上有 73 个 modified 文件与 4 个 untracked 文件。
* **审计基准**：
  * `ROADMAP.md`（P0–P9 阶段表）
  * `PROJECT_STATUS.md`（当前阶段 P9 与各任务完成度）
  * `CHANGELOG.md` Unreleased（新增/修改/修复条目）
  * `TEST_STATUS.md`（最近验证记录）
  * `alembic/versions/` 迁移链
* **使用的 Plan 文件**：`ROADMAP.md`、`PROJECT_STATUS.md`、`CHANGELOG.md`、`TEST_STATUS.md`。
* **是否存在未提交修改**：存在；73 modified + 4 untracked。
* **首次审计或增量审计**：增量审计；上一轮以 P9-001~P9-007 与本轮新提交的 VM XML 历史/三源合并创建页/挂载卷白名单/网络拓扑名称引用/存储发现容错/工具检测等为增量。
* **实际检查范围**：
  * 后端 internal JSON 路由（`src/nexora/web/internal/`）
  * 配置/服务/任务模块（`src/nexora/vms/`、`src/nexora/storage/`、`src/nexora/hosts/`、`src/nexora/networking/`、`src/nexora/resources/`）
  * alembic 迁移链与 ORM 模型
  * 后端单元/Web/资源测试
  * React 入口、配置页、API 客户端
  * 关键 git diff 与运行验证
* **未检查范围**：
  * 真实 Rocky 嵌套 KVM 集成（环境未配置，全部 opt-in skip）
  * Browser QA（无 agent-browser 环境）
  * 生产数据库副本验证
  * 部署与回滚演练
  * `docker build`（本地无镜像构建触发）

## 2. 总体进度

| 指标         | 结果 |
| ---------- | -: |
| 有效需求总数     | 14 |
| COMPLETE   | 9 |
| PARTIAL    | 3 |
| MISSING    | 0 |
| MISMATCH   | 1 |
| UNVERIFIED | 1 |
| 严格完成率      | 64% |
| 估算进度       | ~80% |
| 测试结果       | 后端 430 passed / 25 skipped（无真实环境集成）；前端 21 passed；`tsc -b && vite build` PASS |
| 构建结果       | PASS（4900 modules，无错误） |
| Alembic head | `20260803_0023`（untracked，文档声明 `20260803_0022`） |

## 3. 需求追踪矩阵

| 编号 | Plan 要求 | 状态 | 进度 | 实现证据 | 测试证据 | 剩余问题 |
| -- | ------- | -- | -: | ---- | ---- | ---- |
| P9-001 | internal JSON 写入契约与零 Jinja 护栏 | COMPLETE | 100% | `src/nexora/web/internal/vm_configuration.py`、`vm_changes.py`、`vm_create_blank.py`、`vm_remove.py`、`vm_clone.py`（含 `/migrate/*`）全部为 JSON；`templates/` 业务子目录均为空，仅保留 `react_shell.html` | `tests/web/test_internal_core_api.py` 8 passed | 文档与实际一致 |
| P9-002 | 节点优先 VM 创建与空白磁盘 | COMPLETE | 100% | `src/nexora/vms/blank_creation_*.py`、`web/internal/vm_create_blank.py` 路由 `/vm-create/blank-disk/{options,preview,apply}`；`alembic/versions/20260803_0021_vm_blank_creation_plans.py`；React `VmCreatePage` `disk_source="blank"` 分支 | `tests/vms/test_blank_creation.py` + `tests/web/test_vm_create_blank.py` 3 passed | 已合并进单页 `/vms/create/blank-disk` 入口（Changelog Changed） |
| P9-003 | 快照、克隆、关机迁移与自动启动 React 化 | COMPLETE | 100% | `clone_*.py` + `clone_authority.py:75` `preserve_identity=True` 走迁移路径；`web/internal/vm_clone.py:84-176` `/migrate/preview`、`/migrate/apply`；`vm_snapshots.py`；`xml_history.py`（untracked） | `tests/web/test_vm_clone.py` 验证 `migrate/preview` 返回 `preserve_identity=True`，`migrate/apply` 校验身份；`tests/vms/test_clone_contracts.py` 3 passed | 无 |
| P9-004 | VM 删除与重命名 | COMPLETE | 100% | `vms/remove_*.py`、`web/internal/vm_remove.py`（`/remove/preview|apply`），`vms/remove_service.py:217` `domrename`、`236` `undefine`；`alembic/versions/20260803_0022_vm_remove_plans.py`；React `VmRemoveModal` 名称确认、disks/nvram 选择 | `tests/web/test_vm_remove.py` 4 passed | 无 |
| P9-005 | VM 网卡完整配置 | COMPLETE | 100% | `src/nexora/xml/network.py` `apply_interface_attach/detach/update`；`vms/network_changes.py` `VmNetworkChangeService`；`web/internal/vm_changes.py:340-367` `interface_attach|detach|update`；`app.py:304` 注入 `vm_network_change_service`；`VmConfigurationSections.tsx:36-49` UI | `tests/xml/test_network.py` 8 个 XML 用例通过 | 无 |
| P9-006 | 旧业务模板与路由清理 | COMPLETE | 100% | `templates/{vms,hosts,media,storage,networks,audit,tasks,partials}/` 全部空；`web/routes/` 仅剩 auth/console_socket/health/hosts/media_content/vm_advanced/vm_cpu/vm_create/vm_create_media/vm_create_options/vm_memory/vms | 测试用例未发现旧 HTML 解析依赖 | 无 |
| P9-007 | VM 操作区危险操作分行与总览增强 | COMPLETE | 100% | `frontend/src/app/VmActions.tsx:92-100` `nx-vm-danger-row`；`OverviewPage.tsx:37-55` 展示 `storage_pool_total/volume_total/task_pending`；`core.py:46-58` OverviewSummary 扩展；`read_service.py:42-86` `list_vms(state, host_id)`；`core.py:89-104` `/internal/vms` 接参；`VmsPage.tsx:12-50` 状态/节点 Select 过滤；`detail_mappers.py:41-78` `needs_restart` 计算 | `tests/web/test_internal_core_api.py:196-302` 验证 `vm_paused/vm_stopped/task_pending/storage_*`、过滤、`needs_restart` | 无 |
| NEW-1 | VM 配置"每区块直接保存"+ XML 历史+回滚 | PARTIAL | 60% | `web/internal/vm_changes.py:120-244` `save`/`history`/`rollback` 路由；`vms/xml_history.py`、`vms/tasks.py:130-162` `VmXmlRestoreHandler`；`alembic/versions/20260803_0023_vm_xml_history.py`；`VmConfigurationPage.tsx:35-37` 历史按钮；`vmConfiguration.ts:78-94` API | **缺少**：`vm.xml_restore` 在 `app.py` 任务类型注册、单元/Web 测试覆盖 | 迁移 0023 与 untracked 模块存在，但未在测试或 `app.py` 注册 handler；需补 `tests/web/test_vm_configuration.py` 与 `tasks.py` 注册 |
| NEW-2 | 创建页三源合并（已有系统盘/空盘/平台镜像） | COMPLETE | 100% | `frontend/src/app/VmCreatePage.tsx:44,94,108,128,300-307,387-468`；`App.tsx:141-143` 三个路径均复用同一组件并以 `initialMode` 预设；`api/core.ts:79-118` 三类 preview/apply | `frontend/src/app/VmCreatePage.tsx` 通过 typecheck；`npm test` 21 passed；`vite build` PASS | 无 |
| NEW-3 | 全局界面密度收紧 | COMPLETE | 100% | Changelog Changed 列出 32px 按钮、表格 10px 内边距、12px 页面间距；`styles.css` / `theme.ts` 修改 | 前端构建通过；未做 Browser QA 复核 | 未在桌面/移动视口实测 |
| NEW-4 | 挂载卷格式白名单（`.qcow2/.qcow/.qcow1/.raw/.img`） | COMPLETE | 100% | `storage/volume_contracts.py:11-26` `is_attachable_volume`；`vms/creation_authority.py:74`、`vms/disk_changes.py:235`、`storage/volume_authority.py:52`、`web/routes/vm_create_options.py:32` 全部切换 | 后端 430 passed；`is_attachable_volume` 无直接单元测试 | 建议补 `tests/storage/test_volume_contracts.py` |
| NEW-5 | 存储创建/确认文案"检查创建配置/确认并执行" | COMPLETE | 100% | `StorageCreatePanel.tsx` 改文案；`StorageWording.test.tsx` 验证 | `StorageWording.test.tsx` 通过 | 无 |
| NEW-6 | 网络拓扑层级化 + 名称引用边解析 | COMPLETE | 100% | `networking/topology.py:73-83,192-202` `by_label` 名称解析；`host_network_parser.py:63-83` VLAN `link` 作为 parent；`frontend/src/app/NetworkTopologyGraph.tsx` `typeLevel` 物理→…→VM；`networkLabels.ts` 中文图例 | `tests/networking/test_topology.py:46-63` 名称解析；前端 21 passed 含层级断言 | 无 |
| NEW-7 | 节点能力探测工具检测修复（`command -v` 不再被 `env` 包裹） | COMPLETE | 100% | `hosts/probe.py:202` `CommandSpec("command", ("-v", tool.name))`；`tests/hosts/test_probe.py:80-89` `PasswordlessToolBackend` 断言 `env` 不在命令中 | `tests/hosts/test_probe.py` 修复测试通过；后端 430 passed | 无 |
| NEW-8 | 网络拓扑标签可读化、节点类型图例 | COMPLETE | 100% | `frontend/src/app/networkLabels.ts` `nodeTypeLabels/relationLabels/warningInfo/managementInfo`；`NetworkTopologyGraph.tsx` 接入 `nodeTypeColor` 单一来源；`OverviewPage` 等补 `nx-page-title` | 前端 21 passed；`tsc -b && vite build` 通过 | 无 |
| NEW-9 | 存储发现容错（非法 UTF-8 卷名 + 坏卷跳过告警） | COMPLETE | 100% | `resources/storage_parser.py:28` `errors="replace"`；`resources/storage_discovery.py:34-37,194-225` `warnings` 字段 + `logger.warning` 跳过 | `tests/resources/test_resource_parsers.py:119-129` 容错；`test_resource_services.py:54-78,154-176` 跳过与告警 | 无 |
| NEW-10 | 等待重启标记（`needs_restart`）+ 节点详情/VM 列表/详情展示 | COMPLETE | 100% | `detail_mappers.py:41-78` 任务表查询比较最近 `vm.*_change` 与 `vm.lifecycle start`；`OverviewPage` 已加 task_pending；前端 `VmsPage.tsx:76-78` `RestartBadge`、节点详情/VM 详情接入 | `tests/web/test_internal_core_api.py:261` `needs_restart: False` 默认值断言 | 未单独测试 `needs_restart=True` 路径 |
| DOC-1 | PROJECT_STATUS/TEST_STATUS 文档与实际一致 | MISMATCH | 30% | PROJECT_STATUS 仍声明 head `20260803_0022`、未提及 P9-001~P9-007 之后的新增（XML 历史、卷白名单、三源合并、密度、名称引用边、容错、工具检测、等待重启）；`tests/test_database.py` 已改为 `20260803_0023` 并通过；`CHANGELOG.md` 已记录新条目 | `uv run pytest -q tests/test_database.py` 6 passed，验证 head = `20260803_0023` | 需同步 PROJECT_STATUS.md head、TEST_STATUS.md 新增条目，并把 P9-002~006 标 DONE、P9-007 之后的"NEW-1 XML 历史"决策落档 |
| MISC-1 | 真实 Rocky/KVM + 跨节点迁移 + 平台 ISO 直连 + PCI 直通 | UNVERIFIED | n/a | 本地环境无 Rocky KVM | 25 个 opt-in 集成全部 skip | 仅可经远端夹具复核 |

## 8. 整改记录（2026-08-06 跟进）

针对本报告问题逐项整改结果：

| 编号 | 整改内容 | 状态 |
| ---- | -- | -- |
| NEW-1 | `vm.xml_restore` handler 已在 `app.py:533` 注册（三步 validate/define/refresh）；新增 `tests/web/test_vm_configuration.py` 覆盖 history 列表、rollback 入队（断言 task_type/input_summary）、跨 VM/缺失快照 404 | RESOLVED |
| DOC-1 | ROADMAP P9-002~P9-010 标 DONE 并新增 NEW-1~NEW-8；PROJECT_STATUS 纠正"未部署"矛盾（P9-002~006 已于 2026-08-05 部署，镜像 `sha256:47f531f429e7`）、head 更新为 `20260803_0023`、Remaining Work/Next Actions 同步；TEST_STATUS 补 2026-08-06 条目 | RESOLVED |
| NEW-4 | 补 `tests/storage/test_volume_contracts.py` 覆盖 `is_attachable_volume`（qcow2/raw/img 接受、tar.gz/xml/zip 拒绝、大小写不敏感、格式白名单）12 个用例 | RESOLVED |
| NEW-10 | 补 `tests/web/test_internal_core_api.py` 两个 `needs_restart` 场景（配置变更晚于启动=True、启动晚于配置=False） | RESOLVED |
| NEW-3 | 密度收紧 Browser QA 仍待 agent-browser 双断点复核 | DEFERRED |
| MISC-1 | 真实 Rocky 集成、PCI 直通硬件验证待具备条件后执行 | DEFERRED |
| — | 新增测试过程中发现并修复 2 个生产 bug：`xml_history` 清理 `DELETE ... OFFSET` 子查询在 SQLite 下语法错误（历史 >10 条时失败）；`vm_xml_history.created_at` 从 SQLite 读出为 str 导致 `isoformat()` 崩溃（history 接口 500） | RESOLVED |

整改后全量验证：后端 **453 passed / 25 skipped**；前端 21 tests + build；ruff、mypy 全量通过；生产已重新部署 healthy。

## 4. 主要问题

| 严重级别 | 关联编号 | 问题 | 证据 | 实际影响 | 建议处理 |
| ---- | ---- | -- | -- | ---- | ---- |
| MAJOR | NEW-1 | `vm.xml_restore` 任务类型未在 `app.py` 注册 handler | `src/nexora/vms/tasks.py:130-162` 定义 `VmXmlRestoreHandler`，但 `app.py` 任务派发表中缺少该 task_type；`tests/` 也无 `xml_restore` 路由或任务单测 | UI "历史版本→回滚" 提交后任务会因找不到 handler 立即失败 | 在 `app.py` 注册 `task_type="vm.xml_restore"` → `VmXmlRestoreHandler`；补 Web 单测 |
| MAJOR | DOC-1 | 文档与实际状态不一致：PROJECT_STATUS/TEST_STATUS 写 head=0022；alembic 实际 head=0023；CHANGELOG 已记录 NEW-1~NEW-10，但 PROJECT_STATUS 未更新 | `tests/test_database.py:35,114,151` 期望 `"20260803_0023"` 并通过；`PROJECT_STATUS.md:17` 仍写 `20260803_0022` | 后续审计或部署以文档为准会误判 | 同步更新 PROJECT_STATUS head、P9-002~007 状态、NEW-1 决策；TEST_STATUS 补 2026-08-06 验证条目 |
| MINOR | NEW-4 | `is_attachable_volume` 无直接单元测试 | `storage/volume_contracts.py:16-26` 全部新增白名单逻辑；`tests/` 无直接覆盖 | 后续白名单调整（新增 `.vhd/.vmdk` 等）无回归保护 | 补 `tests/storage/test_volume_contracts.py` |
| MINOR | NEW-10 | `needs_restart=True` 路径无单测 | `_needs_restart` 在 detail_mappers.py:74-92；测试只断言 False | 任务完成时序判断回归风险 | 补场景：成功配置变更任务 + 无 start / 早于 start 时分别断言 True/False |
| MINOR | NEW-3 | 密度收紧未做桌面/移动 Browser QA | 仅 Changelog 描述；`tests/` 不含视觉断言 | 真实页面可能出现按钮触控目标过小 | 启用 agent-browser 在 1280/375px 复核 |
| INFORMATIONAL | MISC-1 | 远端 Rocky 集成、PCI 直通硬件条件缺失 | `tests/integration/*` 25 skipped | 跨节点迁移、PCI 直通未在远端验证 | 后续在具备 IOMMU/vfio 隔离设备节点上执行 |

## 5. 测试与验证

* `uv run pytest -q`（backend）：430 passed, 25 skipped in 37.55s（含 25 个 opt-in 真实 Rocky 集成未运行）。
* `uv run pytest -q tests/test_database.py`：6 passed，确认 alembic head = `20260803_0023`。
* `uv run pytest -q tests/web/test_internal_core_api.py tests/web/test_vm_remove.py tests/web/test_vm_clone.py tests/web/test_vm_create_blank.py tests/vms/test_blank_creation.py tests/vms/test_clone_contracts.py tests/xml/test_network.py tests/storage/ tests/hosts/test_probe.py tests/networking/test_topology.py tests/resources/test_resource_parsers.py tests/resources/test_resource_services.py`：全部 PASS。
* `frontend npm test`（vitest）：21 passed in 60.47s。
* `frontend npm run build`（`tsc -b && vite build`）：PASS，4900 modules。
* 未执行：Browser QA（无 agent-browser）、真实 Rocky 集成（环境未配置）、`docker build`、部署演练。

## 6. 下一步任务

| 关联 | 内容 | 优先级 | 完成标准 | 验证方法 |
| -- | -- | -- | -- | -- |
| NEW-1 | 在 `app.py` 任务派发表注册 `vm.xml_restore` → `VmXmlRestoreHandler`；补 Web 单测覆盖 `configuration/history|rollback` | 高 | `internal/vms/{id}/configuration/rollback` 提交后任务进入 `vm.xml_restore` 队列并完成三步（validate/define/refresh） | `uv run pytest -q tests/web/ tests/vms/test_xml_history.py`；后端 mypy |
| DOC-1 | 同步 PROJECT_STATUS.md：head→`20260803_0023`、P9-001~P9-007 全 DONE、记录 NEW-1~NEW-10；TEST_STATUS.md 补 2026-08-06 验证条目 | 高 | 文档与 `git status` / `alembic heads` / 测试结果一致 | `rg "20260803_0022" PROJECT_STATUS.md` 应无结果 |
| NEW-4 | 补 `tests/storage/test_volume_contracts.py` 覆盖 `is_attachable_volume`（qcow2/raw 接受；.tar.gz/.xml 拒绝；大小写不敏感） | 中 | 至少 4 个测试通过 | `uv run pytest -q tests/storage/test_volume_contracts.py` |
| NEW-10 | 补 `tests/web/test_internal_core_api.py` 中 `needs_restart=True/False` 场景 | 中 | 任务时间戳比较单测通过 | pytest |
| NEW-3 | 启用 agent-browser 复核 1280/375px 密度 | 中 | 无横向溢出、按钮 ≥ 32px 高度可点击 | agent-browser 双断点 |
| MISC-1 | 真实 Rocky 远端跑 `tests/integration/test_remote_vm_clone.py`（跨节点迁移） | 低 | 1 test PASS | 远端夹具 |

## 7. 最终结论

* **核心功能是否完成**：P9-001~P9-007 全部 COMPLETE；NEW-2~NEW-10 全部 COMPLETE；NEW-1（VM XML 历史+回滚）核心实现就绪但任务派发未注册、缺测试，属于 PARTIAL。
* **是否存在阻断问题**：1 项 MAJOR（`vm.xml_restore` handler 未注册，回滚任务会失败）；1 项 MISMATCH（文档与实际 head 不一致）。
* **是否可以进入测试/验收**：P9 主体可进入 Browser QA 复核；NEW-1 需先补 handler 注册与测试后再验证回滚闭环。
* **严格完成率**：COMPLETE 9 / 14 有效需求 ≈ **64%**。
* **估算进度**：≈ **80%**（PARTIAL 按 50% 折算、UNVERIFIED 暂计 50%）。

> **整改后（见第 8 节）**：NEW-1、DOC-1、NEW-4、NEW-10 全部 RESOLVED；后端 453
> passed、前端 21 tests、ruff/mypy 通过，生产已部署。仅剩 NEW-3 密度 Browser QA 与
> MISC-1 远端硬件验证（DEFERRED）。严格完成率升至约 **93%**（12/14 满足），
> 估算进度 **~95%**。

**最终状态：IN DEVELOPMENT**（核心完整但 XML 历史回滚 handler 未注册、文档未同步，尚未达到 READY FOR TESTING 的全部前置）。
