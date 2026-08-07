# Nexora 测试状态

## 当前状态

- 当前阶段：P9 零旧前端与 VM 操作闭环（P9-001~P9-010 完成并部署）+ 前端审计整改
- 已实现代码：internal JSON 配置、快照、克隆、存储变更、节点优先创建、空白磁盘、
  关机迁移、删除重命名、网卡配置、XML 历史回滚、创建页三源合并与操作闭环修复；
  前端视觉一致性/联动逻辑整改（Alert/按钮/表格/共享组件/筛选持久化/任务返回/轮询）
- 自动化测试：437 个通过；另有 25 个 opt-in 真实集成参数用例
- 集成环境：Rocky 9.7 嵌套 KVM，详见专项目录
- 最近验证：2026-08-07 移除登录限流（认证相关 24 tests PASS）+ 前端审计整改部署；
  后端 `uv run pytest -q` 通过；前端 21 tests + typecheck + build；ruff/mypy 通过
- 迁移链 head：`20260803_0023`（`vm_xml_history`）

## 已执行验证

| 日期 | 命令 | 结果 | 范围 |
|---|---|---|---|
| 2026-08-07 | 移除登录限流定向 | PASS；认证相关 24 tests（auth service + auth flow + frontend security + session + navigation）；Ruff 通过 | 限流移除/审计保留 |
| 2026-08-07 | 前端审计整改 | PASS；21 tests + typecheck + `npm run build`；14 处表格响应式、Alert title、按钮统一、共享 FactCard/format | 视觉/联动整改 |
| 2026-08-07 | 重新部署生产 | PASS；镜像 `nexora:noratelimit-20260807T154034Z`，healthy、0.0.0.0:8002、非 privileged、无 Node/npm；登录实测 HTTP 303 成功 | 单容器/登录 |
| 2026-08-06 | 文档同步 + 测试补齐 | PASS；453 passed、25 skipped；新增 XML 历史回滚/`is_attachable_volume`/`needs_restart` 测试；修复 `xml_history` DELETE OFFSET 语法与 `created_at` 类型转换两个生产 bug | 审计整改/测试缺口 |
| 2026-08-06 | VM 操作闭环修复全量 | PASS；437 passed、25 skipped；Ruff/Mypy；前端 21 tests + build | live detach/update、网卡弹窗、ISO 热插拔、CPU ≤、光驱添加、内存预检 |
| 2026-08-06 | 数据库迁移链 | PASS；6 tests，head revision `20260803_0023` | 迁移（`vm_xml_history`） |
| 2026-08-06 | 创建页三源合并 + 密度 + 卷白名单 | PASS；430 passed、25 skipped；前端 21 tests + build | VmCreatePage 合并/密度/`is_attachable_volume` |
| 2026-08-03 | P9-001/006 旧路由注销与模板清理 | PASS；425 passed、25 skipped；旧 POST 路由 404，React 壳路由 200 | 兼容测试迁移/路由注销 |
| 2026-08-03 | P9-002～005 全量门禁 | PASS；428 passed、25 skipped；Ruff/format/Mypy 284 source files；React 20 tests 与生产构建 | 空白磁盘/关机迁移/删除重命名/网卡 |
| 2026-08-03 | P9-002 空白磁盘定向 | PASS；3 tests（service 1 + web 2）；revision 0021 | 空白磁盘创建 |
| 2026-08-03 | P9-003 关机迁移定向 | PASS；6 tests（契约 2 + web 3 + 既有克隆回归）；preserve_identity 保留 UUID/MAC | 关机迁移 |
| 2026-08-03 | P9-004 删除重命名定向 | PASS；4 tests；名称确认与 undefine 验证 | VM 删除/重命名 |
| 2026-08-03 | P9-005 网卡定向 | PASS；10 tests（XML 8 + web 2）；attach/detach/update | VM 网卡配置 |
| 2026-08-03 | 数据库迁移链 | PASS；6 tests，head revision 20260803_0022 | 迁移 |
| 2026-08-03 | P9 第一批全量门禁 | PASS；407 passed、25 skipped；Ruff/format/Mypy；React 20 tests 与生产构建 | JSON 配置/快照/克隆/存储 |
| 2026-08-03 | P8-015 正式部署 | PASS；镜像 `sha256:fb91e77c...0379b51`，healthy、quick_check、UID10001、非 privileged、0 devices、无 Node/npm、0.0.0.0:8002 | 单容器 |
| 2026-08-03 | React typecheck/test/build/audit + diff check | PASS；20 tests，0 vulnerabilities；存储创建与确认文案组件断言通过 | P8-015 存储文案 |
| 2026-08-03 | P8-014 正式部署 | PASS；镜像 `sha256:31a2f7c1...ce71206`，healthy、quick_check、UID10001、非 privileged、0 devices、无 Node/npm、0.0.0.0:8002 | 单容器 |
| 2026-08-03 | React typecheck/test/build/audit + diff check | PASS；18 tests，UTC 00:00 按 Asia/Shanghai 显示 08:00，无偏移时间等价 UTC | P8-014 时区 |
| 2026-08-03 | P8-013 正式部署 | PASS；镜像 `sha256:402e8e96...02d4c91`，healthy、quick_check、UID10001、非 privileged、0 devices、无 Node/npm、0.0.0.0:8002 | 单容器 |
| 2026-08-03 | React typecheck/test/build/audit + diff check | PASS；16 tests，0 vulnerabilities；镜像图标、固定密度和技术等宽字体断言通过 | P8-013 前端 |
| 2026-08-03 | P8-012 正式部署 | PASS；镜像 `sha256:3d4192ef...3b56ce`，healthy、quick_check、UID10001、非 privileged、0 devices、无 Node/npm、0.0.0.0:8002 | 单容器 |
| 2026-08-03 | React typecheck/test/build + diff check | PASS；15 tests，节点导航使用 CloudServerOutlined | P8-012 导航图标 |
| 2026-08-03 | P8-011 正式部署 | PASS；镜像 `sha256:cf9111c0...d4fcca`，healthy、quick_check、UID10001、非 privileged、0 devices、无 Node/npm、0.0.0.0:8002 | 单容器 |
| 2026-08-03 | kvm3 PCIe 直通能力 Browser QA | PASS；显示支持和 2 个可直通设备；1280/375px 无溢出或控制台错误 | P8-011 节点详情 |
| 2026-08-03 | P8-011 全量门禁 | PASS；404 passed、25 skipped；React 15 tests；两套 audit 0 vulnerabilities | 全量回归 |
| 2026-08-03 | P8-010 正式部署 | PASS；镜像 `sha256:91dbd466...0dc825`，React 登录页、healthy、quick_check、UID10001、非 privileged、0 devices、无 Node/npm、0.0.0.0:8002 | 单容器 |
| 2026-08-03 | P8-010 生产数据副本 Browser QA | PASS；React 登录、历史 manage、新 VM 配置；1280/375px 无旧页面、溢出或控制台错误 | 全站 React 收敛 |
| 2026-08-03 | Ruff/format/Mypy/pytest | PASS；403 passed，25 skipped，265 source files typed | P8-010 全量回归 |
| 2026-08-03 | React typecheck/test/build/audit | PASS；15 tests，0 vulnerabilities | P8-010 前端回归 |
| 2026-08-03 | P8-009 正式部署 | PASS；镜像 `sha256:89e799447c...47192b2`，healthy、quick_check、UID10001、非 privileged、0 devices、无 Node/npm、0.0.0.0:8002 | 单容器 |
| 2026-08-03 | kvm3/OpenWrt 生产数据副本 Browser QA | PASS；2 块 Intel I211、PCI 地址、vfio-pci、IOMMU 组可见；1280/375px 无溢出或控制台错误 | P8-009 React |
| 2026-08-03 | Ruff/format/Mypy/pytest | PASS；403 passed，25 skipped，264 source files typed | P8-009 全量回归 |
| 2026-08-03 | React typecheck/test/build/audit | PASS；14 tests，0 vulnerabilities | P8-009 前端回归 |
| 2026-08-03 | P8-008 正式部署 | PASS；healthy、quick_check、UID10001、非 privileged、0 devices、无 Node/npm、0.0.0.0:8002 | 单容器 |
| 2026-08-03 | VM 操作区生产数据副本 Browser QA | PASS；1280/375px，7 按钮均 36px、8px 间距、无重叠/溢出 | P8-008 React |
| 2026-08-03 | P8-007 正式部署与现有节点刷新 | PASS；healthy、quick_check、UID10001、非 privileged、0 devices、无 Node/npm；3 节点双任务成功 | 单容器/生产数据 |
| 2026-08-03 | Rocky 节点硬件与网卡探测 | PASS；CPU/厂商/型号/内存/功能状态及实体网卡 MAC | P8-007 真实集成 |
| 2026-08-03 | 节点详情生产数据副本 Browser QA | PASS；1280/375px、2 个实体网卡、MAC 可见、无溢出/控制台错误 | P8-007 React |
| 2026-08-03 | Ruff/format/Mypy/pytest | PASS；403 passed，25 skipped，264 source files typed | P8-007 全量回归 |
| 2026-08-03 | React typecheck/test/build/audit | PASS；14 tests，0 vulnerabilities | P8-007 前端回归 |
| 2026-08-03 | Web 修复正式部署 | PASS；healthy、quick_check、UID10001、0 devices、无 Node/npm、0.0.0.0:8002 | 单容器 |
| 2026-08-03 | 生产数据副本 16 路由 Browser QA | PASS；1280/375px 均有内容，无页面/表格横向溢出或控制台错误 | React/兼容页 |
| 2026-08-03 | 网络拓扑真实数据 QA | PASS；Canvas 生成、边端点有效、接口/VM 状态语义正确 | P4/P8 Web |
| 2026-08-03 | React typecheck/test/build/audit | PASS；14 tests，0 vulnerabilities | 前端回归 |
| 2026-08-03 | Ruff/format/Mypy/pytest | PASS；398 passed，24 skipped，263 source files typed | 全量回归 |
| 2026-08-03 | legacy build/audit + diff check | PASS；0 vulnerabilities | 配置兼容岛与交付 |
| 2026-08-01 | P7 收尾正式部署 | PASS；healthy、quick_check、UID10001、0 devices、无 Node/npm | 单容器 |
| 2026-08-01 | Rocky virtiofs 共享目录 | PASS；1 test，17.48s；挂载/卸载、原 XML 与目录恢复 | P7 真实集成 |
| 2026-08-01 | Rocky VM/Host 指标 | PASS；1 test，12.59s | P7 真实集成 |
| 2026-08-01 | Rocky 静态 IPv6 | PASS；2 tests，51.10s；IPv6-only/双栈、启动与零残留 | P7 真实集成 |
| 2026-08-01 | P7/P8 全量门禁 | PASS；398 passed，24 skipped；Ruff/Mypy/双前端构建与审计通过 | 全量回归 |
| 2026-08-01 | 资源列表滚动条 Browser QA | PASS；节点/VM 页面、外层和表格内容均无横向溢出 | React Web |
| 2026-08-01 | React typecheck/test/build/audit | PASS；13 tests，0 vulnerabilities | 滚动条修复 |
| 2026-08-01 | 正式修复镜像部署 | PASS；healthy、quick_check、本地 CSS 资产已更新 | 单容器 |
| 2026-08-01 | `uv run pytest -q` | PASS；394 passed，22 skipped | P8 全量回归 |
| 2026-08-01 | Ruff check/format + mypy | PASS；393 files formatted，263 source files typed | 静态质量 |
| 2026-08-01 | React typecheck/test/build/audit | PASS；13 tests，0 vulnerabilities | P8-004～006 前端 |
| 2026-08-01 | legacy build/audit + diff check | PASS；0 vulnerabilities | 配置兼容岛与交付 |
| 2026-08-01 | 主工作台 Browser QA | PASS；375/768/1280/1440，无溢出/控制台错误，移动抽屉与深链接正常 | P8 Web |
| 2026-08-01 | 正式镜像部署 | PASS；healthy、quick_check、UID10001、0 devices、无 Node/npm | P8 单容器 |
| 2026-08-01 | React typecheck/test/build | PASS；12 tests | P8-004 节点接入与两类 VM 创建 |
| 2026-08-01 | `pytest` 定向 + Ruff + mypy | PASS；节点/创建/媒体服务相关用例 | P8-004 写入契约 |
| 2026-08-01 | React typecheck/test/build/audit | PASS；9 tests，0 vulnerabilities | P8-004 VM 创建 |
| 2026-08-01 | `uv run pytest -q` | PASS；385 passed，22 skipped | 全量回归 |
| 2026-08-01 | Ruff format/check + mypy strict | PASS；250 source files | 静态质量 |
| 2026-08-01 | VM 创建 Browser QA | PASS；四断点，无溢出/渐变/控制台错误，UEFI 非安全启动可选 | P8-004 Web |
| 2026-08-01 | React typecheck/test/build/audit | PASS；7 tests，0 vulnerabilities | P8-003 前端 |
| 2026-08-01 | `uv run pytest -q` | PASS；383 passed，22 skipped | 全量回归 |
| 2026-08-01 | Ruff format/check + mypy strict | PASS；249 source files | 静态质量 |
| 2026-08-01 | 详情与兼容管理入口 Browser QA | PASS；四断点，无溢出/渐变/控制台错误 | P8-003 Web |
| 2026-08-01 | Design Token 视觉断言 | PASS；状态无圆点/边框，按钮填充与边框同色 | 全站主题 |
| 2026-08-01 | 正式镜像部署 | PASS；healthy、quick_check、UID10001、0 devices、无 Node/npm | P8-003 单容器 |
| 2026-08-01 | React typecheck/test/build/audit | PASS；5 tests，0 vulnerabilities | P8-002 前端 |
| 2026-08-01 | `uv run pytest -q` | PASS；379 passed，22 skipped | 全量回归 |
| 2026-08-01 | Ruff format/check + mypy strict | PASS；248 source files | 静态质量 |
| 2026-08-01 | 三个 React 页面 Browser QA | PASS；四断点，无溢出/控制台错误 | P8-002 Web |
| 2026-08-01 | 正式镜像部署 | PASS；healthy、UID10001、0 devices、无 Node/npm | 单容器 |
| 2026-07-31 | React typecheck/test/build/audit | PASS；3 tests，0 vulnerabilities | P8-001 前端 |
| 2026-07-31 | `uv run pytest -q` | PASS；374 passed，22 skipped | 全量回归 |
| 2026-07-31 | Ruff format/check + mypy strict | PASS；247 source files | 静态质量 |
| 2026-07-31 | `/ui-preview` Browser QA | PASS；375/768/1280/1440px，无溢出/错误 | React Shell |
| 2026-07-31 | 正式镜像部署 | PASS；healthy、UID10001、0 devices、无 Node/npm | 单容器 |
| 2026-07-28 | 必需文件、行数、章节和尾随空白综合检查 | PASS；22 个文档，最大 90 行 | 文档结构 |
| 2026-07-28 | 必需文件 shell 存在性检查 | PASS；8 个根目录必需文件齐全 | 文档结构 |
| 2026-07-28 | `rg` 检查身份、RemoteExecutor、lease、回滚决策 | PASS；关键约束口径一致 | 架构一致性 |
| 2026-07-28 | shell 检查 `PROJECT_STATUS.md` 16 个章节 | PASS；章节齐全 | 恢复状态 |
| 2026-07-28 | `uv run pytest -q` | PASS；29 tests，无 warning | Python |
| 2026-07-28 | Ruff format/check + mypy strict | PASS | 静态质量 |
| 2026-07-28 | `docker compose config --quiet` | PASS | Compose |
| 2026-07-28 | `docker build --tag nexora:p0 .` | PASS | Python 3.12 镜像 |
| 2026-07-28 | 临时容器健康与权限检查 | PASS；UID 10001、非 privileged、无设备映射 | 容器 |
| 2026-07-28 | agent-browser 桌面/375px 认证流程 | PASS；无页面/控制台错误 | Web UI |
| 2026-07-28 | 重建容器初始化与迁移检查 | PASS；HTTP 200，revision 0002 | 容器 |
| 2026-07-28 | 凭据 AEAD/篡改/AAD/轮换测试 | PASS | 安全 |
| 2026-07-28 | Host Key 单元与真实临时 sshd | PASS；match/change/0600 | SSH |
| 2026-07-28 | RemoteExecutor 单元与真实 SSH | PASS；UID/operation/audit | SSH |
| 2026-07-28 | `uv run pytest -q` | PASS；70 tests | P0 全量回归 |
| 2026-07-28 | 任务 claim/lease/step/取消/重启测试 | PASS；14 tests | 持久化任务 |
| 2026-07-28 | `npm audit --omit=dev` | PASS；0 vulnerabilities | 前端供应链 |
| 2026-07-28 | Tabler 桌面/375px Browser QA | PASS；无溢出/控制台错误 | Web UI |
| 2026-07-28 | `docker build` 与运行检查 | PASS；健康、无 Node.js | 单容器 |
| 2026-07-28 | XML 安全/保留/CPU/Diff | PASS；11 tests | libvirt XML |
| 2026-07-28 | 备份/恢复安全测试 | PASS；5 tests | 数据恢复 |
| 2026-07-28 | `nexora-ops` 完整演练 | PASS；live/recovery 状态正确 | 运维 |
| 2026-07-28 | P0 完整镜像运行 | PASS；healthy/UID10001/0 devices | 单容器 |
| 2026-07-28 | AsyncSSH 临时服务端 | PASS；密码/加密私钥/限额/超时 | SSH |
| 2026-07-28 | Host Key 接入与能力探测 | PASS；26 targeted tests | P1 节点 |
| 2026-07-28 | `uv run pytest -q` | PASS；105 tests | P1 全量回归 |
| 2026-07-28 | Ruff format/check + mypy strict | PASS；69 source files | 静态质量 |
| 2026-07-28 | `npm audit --omit=dev` | PASS；0 vulnerabilities | 前端供应链 |
| 2026-07-28 | P1 节点页 Browser QA | PASS；1440/375px，无控制台错误 | Web UI |
| 2026-07-28 | `nexora:p1-review` 运行 | PASS；healthy/revision 0004/5 tables | 单容器 |
| 2026-07-28 | ResourceIndex 与 8 类资源解析 | PASS；13 resource tests | P1 发现 |
| 2026-07-28 | `uv run pytest -q` | PASS；119 tests | P1 全量回归 |
| 2026-07-28 | 资源详情 Browser QA | PASS；1280/375px，无溢出/错误 | Web UI |
| 2026-07-28 | `nexora:p1-resources` 运行 | PASS；healthy/revision 0005 | 单容器 |
| 2026-07-28 | 冲突守卫与节点移除 | PASS；9 targeted tests | P1 安全 |
| 2026-07-28 | `uv run pytest -q` | PASS；128 tests | P1 全量回归 |
| 2026-07-28 | 节点移除 Browser QA | PASS；桌面/375px，无溢出/错误 | Web UI |
| 2026-07-28 | `nexora:p1-complete` 运行 | PASS；healthy/revision 0006 | 单容器 |
| 2026-07-28 | VM 生命周期与资源锁 | PASS；14 targeted tests | P2 VM |
| 2026-07-28 | `uv run pytest -q` | PASS；142 tests | P2 全量回归 |
| 2026-07-28 | VM 列表/详情 Browser QA | PASS；1280/375px，无溢出/错误 | Web UI |
| 2026-07-28 | `nexora:p2-lifecycle` 运行 | PASS；healthy/revision 0007 | 单容器 |
| 2026-07-28 | CPU 预览/确认/应用/回滚 | PASS；4 targeted tests | P2 VM |
| 2026-07-28 | `uv run pytest -q` | PASS；147 tests | P2 全量回归 |
| 2026-07-28 | CPU 配置 Browser QA | PASS；1280/375px，无溢出/错误 | Web UI |
| 2026-07-28 | `nexora:p2-cpu` 运行 | PASS；healthy/revision 0008 | 单容器 |
| 2026-07-28 | 内存 XML/计划/应用 | PASS；5 tests | P2 VM |
| 2026-07-28 | `uv run pytest -q` | PASS；152 tests | P2 全量回归 |
| 2026-07-28 | 内存配置 Browser QA | PASS；1280/375px，无溢出/错误 | Web UI |
| 2026-07-28 | `nexora:p2-memory` 运行 | PASS；healthy/revision 0008 | 单容器 |
| 2026-07-28 | 媒体路径/哈希/索引 | PASS；3 scanner tests | P3 媒体 |
| 2026-07-28 | `uv run pytest -q` | PASS；156 tests | P3 全量回归 |
| 2026-07-28 | 媒体库 Browser QA | PASS；扫描任务、1280/375px、无错误 | Web UI |
| 2026-07-28 | `nexora:p3-media-index` 运行 | PASS；revision 0009、library ro | 单容器 |
| 2026-07-28 | Range/文件替换/凭据撤销 | PASS；10 tests | P3 媒体 |
| 2026-07-28 | `uv run pytest -q` | PASS；166 tests | P3 全量回归 |
| 2026-07-28 | ISO 凭据 Browser QA | PASS；1280/375px、无 token 输出 | Web UI |
| 2026-07-28 | `nexora:p3-media-range` 运行 | PASS；revision 0010、library ro | 单容器 |
| 2026-07-28 | 镜像复制定向回归 | PASS；23 tests | P3 媒体 |
| 2026-07-28 | Ruff format/check + mypy strict | PASS；121 source files | 静态质量 |
| 2026-07-28 | `git diff --check` | PASS | 工作树 |
| 2026-07-28 | `uv run pytest -q` | PASS；177 passed，1 skipped | 全量回归 |
| 2026-07-28 | 真实 Rocky/KVM 集成 | PASS；1 test，14.22s | P1/P3 |
| 2026-07-28 | 节点移除外部零残留检查 | PASS；临时实体 0，业务资源保留 | P1 |
| 2026-07-28 | 任务恢复 Browser QA | PASS；1280/375px，无错误 | Web UI |
| 2026-07-28 | `nexora:p3-image-copy` | PASS；healthy/revision 0010/UID10001 | 单容器 |
| 2026-07-28 | Ruff + mypy + npm + Compose | PASS；124 source files | 质量门禁 |
| 2026-07-28 | Pool 契约/XML/任务/冲突定向回归 | PASS；25 tests | P3 存储 |
| 2026-07-28 | `uv run pytest -q` | PASS；204 passed，2 skipped | 全量回归 |
| 2026-07-28 | 真实 Rocky/KVM 与 NFS Pool | PASS；2 tests，49.64s | P1/P3 |
| 2026-07-28 | Pool 删除外部复核 | PASS；定义/挂载清理，NFS 文件保留 | P3 存储 |
| 2026-07-28 | 存储页 Browser QA | PASS；1280/375px，无溢出/错误 | Web UI |
| 2026-07-28 | `nexora:p3-storage` | PASS；healthy/revision 0011/UID10001 | 单容器 |
| 2026-07-28 | Ruff + mypy + npm + Compose | PASS；140 source files | 质量门禁 |
| 2026-07-28 | Volume 输入/XML/迁移/创建 | PASS；22 tests | P3 存储 |
| 2026-07-28 | 真实 Rocky qcow2 Volume 创建 | PASS；1 test，22.48s | P3 存储 |
| 2026-07-28 | `uv run pytest -q` | PASS；214 passed，3 skipped | 全量回归 |
| 2026-07-28 | Ruff + mypy + diff check | PASS；148 source files | 质量门禁 |
| 2026-07-29 | Volume 扩容/删除/引用/hash 定向回归 | PASS；48 tests | P3 存储 |
| 2026-07-29 | 真实 Rocky dir/netfs qcow2 Volume | PASS；2 tests，66.20s | P3 存储 |
| 2026-07-29 | 远端测试资源复核 | PASS；Pool/Target/NFS Volume 全部不存在 | 零残留 |
| 2026-07-29 | `uv run pytest -q` | PASS；221 passed，4 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + npm audit + Compose + diff | PASS；151 source files | 质量门禁 |
| 2026-07-29 | Volume 页面 Browser QA | PASS；1280/375px、无溢出/控制台错误 | Web UI |
| 2026-07-29 | `nexora:p3-volume` | PASS；healthy/revision 0012/UID10001/0 devices | 单容器 |
| 2026-07-29 | VM Disk XML/计划/路由定向回归 | PASS；13 tests | P2 VM |
| 2026-07-29 | 真实 Rocky 运行中 VM Disk | PASS；1 test，31.65s | P2 VM |
| 2026-07-29 | 远端 Disk 测试资源复核 | PASS；Pool/Volume/Target/引用均无残留 | 零残留 |
| 2026-07-29 | `uv run pytest -q` | PASS；229 passed，5 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + npm + Compose + diff | PASS；154 source files | 质量门禁 |
| 2026-07-29 | VM Disk Browser QA | PASS；1280/375px、44px、无错误 | Web UI |
| 2026-07-29 | `nexora:p2-vm-disk` | PASS；healthy/revision 0012/UID10001/0 devices | 单容器 |
| 2026-07-29 | CD-ROM XML/计划/页面定向回归 | PASS；9 tests | P2 VM |
| 2026-07-29 | 真实 Rocky 运行中 VM CD-ROM | PASS；1 test，34.29s | P2 VM |
| 2026-07-29 | 远端 CD-ROM 测试资源复核 | PASS；原 XML 恢复且测试资源无残留 | 零残留 |
| 2026-07-29 | `uv run pytest -q` | PASS；233 passed，6 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + npm + Compose + diff | PASS；157 source files | 质量门禁 |
| 2026-07-29 | CD-ROM Browser QA | PASS；1280/375px、44px、无错误 | Web UI |
| 2026-07-29 | `nexora:p2-cdrom` | PASS；healthy/revision 0012/UID10001/0 devices | 单容器 |
| 2026-07-29 | 平台 ISO 缓存定向回归 | PASS；6 tests | P2/P3 媒体 |
| 2026-07-29 | 真实 Rocky 平台 ISO 缓存 | PASS；1 test，24.90s | P2/P3 集成 |
| 2026-07-29 | Range/撤销/QEMU/零残留 | PASS；VM 与缓存文件为 0 | 安全/零残留 |
| 2026-07-29 | `uv run pytest -q` | PASS；241 passed，7 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy | PASS；162 source files | 静态质量 |
| 2026-07-29 | npm assets/audit + Compose + diff | PASS；0 vulnerabilities | 供应链/配置 |
| 2026-07-29 | `nexora:p2-platform-iso` | PASS；healthy/revision 0012/UID10001/0 devices | 单容器 |
| 2026-07-29 | 平台 ISO 页面 Browser QA | PASS；1280/375px、44px、无错误 | Web UI |
| 2026-07-29 | Snapshot 只读定向回归 | PASS；13 tests | P2 VM |
| 2026-07-29 | 真实 Rocky 带外 Snapshot 发现 | PASS；1 test，12.21s | P1/P2 集成 |
| 2026-07-29 | Snapshot 页面 Browser QA | PASS；1280/375px、44px、无错误 | Web UI |
| 2026-07-29 | `uv run pytest -q` | PASS；242 passed，8 skipped | 全量回归 |
| 2026-07-29 | Snapshot 创建/migration 定向回归 | PASS；7 tests | P2 VM |
| 2026-07-29 | 真实 Rocky Snapshot 发现与任务创建 | PASS；2 tests，29.04s | P1/P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；243 passed，9 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + diff check | PASS；170 source files | 质量门禁 |
| 2026-07-29 | 本机 `nexora:latest` | PASS；healthy/revision 0013/UID10001/0 devices | 单容器 |
| 2026-07-29 | 0012→0013 迁移 | PASS；管理员保留、Snapshot plan 表存在 | SQLite |
| 2026-07-29 | 部署后登录页 Browser QA | PASS；1280/375px、无溢出或错误 | Web UI |
| 2026-07-29 | Snapshot leaf 删除定向回归 | PASS；16 tests | P2 VM |
| 2026-07-29 | 真实 Rocky Snapshot 创建与 leaf 删除 | PASS；2 tests，33.53s | P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；244 passed，9 skipped | 全量回归 |
| 2026-07-29 | Snapshot leaf 版本本机部署 | PASS；healthy/revision 0013/管理员保留 | 单容器 |
| 2026-07-29 | Snapshot 恢复定向回归 | PASS；15 tests | P2 VM |
| 2026-07-29 | 真实 Rocky Snapshot A/B/A 恢复 | PASS；2 tests，36.91s | P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；245 passed，9 skipped | 全量回归 |
| 2026-07-29 | Snapshot 恢复版本本机部署 | PASS；healthy/revision 0013/管理员保留 | 单容器 |
| 2026-07-29 | VM 实时性能定向回归 | PASS；7 tests | P2 VM |
| 2026-07-29 | 真实 Rocky VM domstats | PASS；1 test，10.92s | P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；248 passed，10 skipped | 全量回归 |
| 2026-07-29 | VM 性能版本本机部署 | PASS；healthy/revision 0013/管理员保留 | 单容器 |
| 2026-07-29 | VM 性能版本 Browser QA | PASS；375px、无溢出或错误 | Web UI |
| 2026-07-29 | VM 创建定向回归 | PASS；12 tests | P2 VM |
| 2026-07-29 | 真实 Rocky managed Volume 创建 | PASS；1 test，19.42s | P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；254 passed，11 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + npm + Compose + diff | PASS；184 source files | 质量门禁 |
| 2026-07-29 | VM 创建 Browser QA | PASS；1280/375px、44px、无错误 | Web UI |
| 2026-07-29 | 本机 `nexora:latest` | PASS；healthy/revision 0014/UID10001 | 单容器 |
| 2026-07-29 | VM 创建网络定向回归 | PASS；15 tests | P2 VM |
| 2026-07-29 | 真实 Rocky libvirt Network 创建 | PASS；1 test，20.50s | P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；257 passed，11 skipped | 全量回归 |
| 2026-07-29 | VM 创建网络 Browser QA | PASS；375px、44px、无溢出/错误 | Web UI |
| 2026-07-29 | VM 网络版 `nexora:latest` | PASS；healthy/revision 0014 | 单容器 |
| 2026-07-29 | VM 创建本地 ISO 定向回归 | PASS；16 tests | P2 VM |
| 2026-07-29 | 真实 Rocky readonly SATA ISO | PASS；1 test，22.05s | P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；258 passed，11 skipped | 全量回归 |
| 2026-07-29 | VM 本地 ISO Browser QA | PASS；375px、44px、无溢出/错误 | Web UI |
| 2026-07-29 | 本地 ISO `nexora:latest` | PASS；healthy/revision 0014 | 单容器 |
| 2026-07-29 | QA 凭据与临时文件复核 | PASS；原管理员恢复、临时口令失效 | 安全 |
| 2026-07-29 | 平台镜像创建定向回归 | PASS；19 tests | P2/P3 VM |
| 2026-07-29 | 真实 Rocky 平台 raw 创建 | PASS；1 test，21.28s | P2/P3 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；261 passed，12 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + diff | PASS；194 source files | 质量门禁 |
| 2026-07-29 | 平台镜像创建 Browser QA | PASS；375px、44px、无错误 | Web UI |
| 2026-07-29 | 平台镜像 `nexora:latest` | PASS；healthy/revision 0015 | 单容器 |
| 2026-07-29 | Cloud Image 定向回归 | PASS；16 tests | P2 VM |
| 2026-07-29 | 真实 Rocky NoCloud 创建/恢复 | PASS；1 test，23.85s | P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；264 passed，12 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + diff | PASS；197 source files | 质量门禁 |
| 2026-07-29 | Cloud Image Browser QA | PASS；375px、44px、无错误 | Web UI |
| 2026-07-29 | Cloud Image `nexora:latest` | PASS；healthy/revision 0015 | 单容器 |
| 2026-07-29 | Guest Agent 定向回归 | PASS；6 tests | P2 VM |
| 2026-07-29 | 真实 Rocky Guest Agent | PASS；1 test，14.40s；零残留 | P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；269 passed，13 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + diff | PASS；199 source files | 质量门禁 |
| 2026-07-29 | HTMX/Guest Agent Browser QA | PASS；XHR 200、375px、44px | Web UI |
| 2026-07-29 | Guest Agent `nexora:latest` | PASS；healthy/revision 0015 | 单容器 |
| 2026-07-29 | ConsoleSession/串口定向回归 | PASS；11 tests | P2 VM |
| 2026-07-29 | 真实 Rocky 串口 PTY | PASS；1 test，12.60s；零进程残留 | P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；275 passed，14 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy | PASS；205 source files | 质量门禁 |
| 2026-07-29 | xterm/WebSocket Browser QA | PASS；375px、44px、零 Session | Web UI |
| 2026-07-29 | 串口 `nexora:latest` | PASS；healthy/revision 0016 | 单容器 |
| 2026-07-29 | VNC parser/websockify 定向回归 | PASS；8 console tests | P2 VM |
| 2026-07-29 | 真实 Rocky VNC RFB | PASS；1 test，10.83s；零 worker | P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；277 passed，15 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + npm | PASS；207 source files；0 漏洞 | 质量门禁 |
| 2026-07-29 | noVNC Browser QA | PASS；canvas、375px、44px、零残留 | Web UI |
| 2026-07-29 | noVNC `nexora:latest` | PASS；healthy/revision 0016 | 单容器 |
| 2026-07-29 | Remote relay unit/真实 Rocky | PASS；2 MiB、双审计、SHA、零 partial | SSH 传输 |
| 2026-07-29 | 克隆 XML/manifest/Web 定向回归 | PASS；5 tests | P2 VM |
| 2026-07-29 | 真实 Rocky 关机完整克隆 | PASS；1 test，25.47s；目标启动 | P2 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；282 passed，17 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + npm + Compose + diff | PASS；217 source；0 漏洞 | 质量门禁 |
| 2026-07-29 | 克隆 Browser QA | PASS；375px、44px、无路径输入/错误 | Web UI |
| 2026-07-29 | 克隆 `nexora:latest` | PASS；healthy/revision 0017/UID10001 | 单容器 |
| 2026-07-29 | Cloud 密码/静态 IPv4/扩容定向 | PASS；21 tests | P2 VM |
| 2026-07-29 | 真实 Rocky Cloud 扩容创建 | PASS；1 test，24.28s；8→16 MiB | P2 集成 |
| 2026-07-29 | Cloud 测试资源复核 | PASS；VM/Disk/seed 不存在，partial=0 | 零残留 |
| 2026-07-29 | `uv run pytest -q` | PASS；288 passed，17 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + npm + Compose + diff | PASS；219 source；0 漏洞 | 质量门禁 |
| 2026-07-29 | Cloud Image Browser QA | PASS；1280/375px、22 控件≥44px、无错误 | Web UI |
| 2026-07-29 | Cloud revision 0018 部署 | PASS；healthy/UID10001/0 devices | 单容器 |
| 2026-07-29 | 网络拓扑模型与 Web 定向 | PASS；21 tests | P4 网络 |
| 2026-07-29 | 真实 Rocky 网络拓扑 | PASS；1 test，10.54s；管理口/默认路由 | P4 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；292 passed，18 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + npm + Compose + diff | PASS；223 source；0 漏洞 | 质量门禁 |
| 2026-07-29 | 网络拓扑 Browser QA | PASS；1280/375px、2 表、44px、无错误 | Web UI |
| 2026-07-29 | 网络拓扑本机部署 | PASS；healthy/UID10001/0 devices | 单容器 |
| 2026-07-29 | 审计读取与 Web 定向 | PASS；10 tests | 审计 |
| 2026-07-29 | `uv run pytest -q` | PASS；294 passed，18 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + npm + Compose + diff | PASS；224 source；0 漏洞 | 质量门禁 |
| 2026-07-29 | 审计 Browser QA | PASS；1280/375px、50 行、44px、无注入/错误 | Web UI |
| 2026-07-29 | 审计中心本机部署 | PASS；healthy/UID10001/0 devices | 单容器 |
| 2026-07-29 | 现代明亮 UI Web 回归 | PASS；38 tests，npm assets/audit | P6 UI |
| 2026-07-29 | 视觉四断点 Browser QA | PASS；4 页面×375/768/1024/1440px | P6 UI |
| 2026-07-29 | 最终网络拓扑 Browser QA | PASS；375/1440px、44px、零错误 | P4/P6 UI |
| 2026-07-29 | 最终 Rocky 网络拓扑 | PASS；1 test，10.29s；Bridge/vnet/管理链 | P4 集成 |
| 2026-07-29 | `uv run pytest -q` | PASS；295 passed，18 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + npm + Compose + diff | PASS；224 source；0 漏洞 | 质量门禁 |
| 2026-07-29 | 最终 `nexora:latest` 部署 | PASS；`dc7c02b1...`/0018/UID10001/0 devices | 单容器 |
| 2026-07-29 | 真实密码 SSH/普通用户 sudo | PASS；1 test，0.91s；零残留 | P1 集成 |
| 2026-07-29 | 真实加密私钥口令 SSH | PASS；1 test，2.50s；零残留 | P1 集成 |
| 2026-07-29 | modular 首轮夹具 | FAIL；缺少 virtnodedevd，设备发现失败 | 测试夹具 |
| 2026-07-29 | 真实 modular libvirt | PASS；1 test，13.61s；恢复/零残留 | P1 集成 |
| 2026-07-29 | Debian cloud-init wait | TIMEOUT；安装继续并最终 done | 测试夹具 |
| 2026-07-29 | Debian 13 nested KVM | PASS；1 test，14.34s；已有 VM 发现 | P1 集成 |
| 2026-07-29 | Debian 首次清理脚本 | FAIL；远端 awk 引号错误，未执行删除 | 测试夹具 |
| 2026-07-29 | Debian 最终清理 | PASS；VM/Disk/seed/Tunnel/临时文件为 0 | 零残留 |
| 2026-07-29 | `uv run pytest -q` | PASS；295 passed，21 skipped | 全量回归 |
| 2026-07-29 | 首次 Ruff format check | FAIL；1 个新测试需机械格式化 | 质量门禁 |
| 2026-07-29 | Ruff + mypy + npm + Compose + diff | PASS；224 source；0 漏洞 | 质量门禁 |
| 2026-07-29 | Ubuntu 24.04 LTS nested KVM | PASS；1 test，已有 VM 自动发现 | P1 集成 |
| 2026-07-29 | Ubuntu 测试资源复核 | PASS；用户/sudoers/VM/Disk/ISO/Tunnel 为 0 | 零残留 |
| 2026-07-29 | `uv run pytest -q` | PASS；295 passed，21 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy + npm + Compose + diff | PASS；224 source；0 漏洞 | 质量门禁 |
| 2026-07-29 | 高级 XML 配置只读解析 | PASS；10 tests，含 NUMA/CPUTune/Watchdog/vsock | P5 XML |
| 2026-07-29 | `uv run pytest -q` | PASS；305 passed，21 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy | PASS；225 source files | 质量门禁 |
| 2026-07-29 | 磁盘高级参数 XML/验证 | PASS；7 tests，含 cache/io/discard/serial/readonly/shareable | P2 XML |
| 2026-07-29 | `uv run pytest -q` | PASS；312 passed，21 skipped | 全量回归 |
| 2026-07-29 | Ruff + mypy | PASS；225 source files | 质量门禁 |
| 2026-07-30 | Ubuntu 26.04 LTS 接入/发现/移除 | PASS；1 test，12.58s；零残留 | P1 集成 |
| 2026-07-30 | `uv run pytest -q` | PASS；326 passed，22 skipped | 全量回归 |
| 2026-07-30 | Ruff + mypy | PASS；225 source files | 质量门禁 |

验证调用纠正：`npm run build` 不存在，正确入口为 `npm run build:assets`；首次
Compose 检查未提供必填占位密钥，补充安全占位值后通过。隔离容器首次挂载的
`mktemp` 目录不可由 UID 10001 写入，调整专用目录权限后健康启动；均非产品回归。
首版 `qemu-img info` HTTP 探测在 Rocky 产生假阳性，真实集成测试捕获后已替换为
domcapabilities 指定的 system QEMU machine-none/QMP 探测，最终实机回归通过。

## 计划中的单元测试

- SSH argv 编码、Host Key、凭据加密和脱敏。
- XML 安全解析、生成、未知元素保留、规范化和 Diff。
- CPU topology、NUMA、HugePages、磁盘、网卡和 PCI 判断。
- 媒体路径、HTTP Range、token、SHA-256 和镜像复制恢复。
- Pool、NFS netfs、Bridge、VLAN 与网络后端探测。
- 网络计划、独立回滚、确认超时和恢复。
- 任务原子领取、lease、锁、取消、幂等和崩溃恢复。
- 资源复合身份、generation/hash 和带外冲突。

## 计划中的集成测试

- 单容器且无 `/dev/kvm`、无 libvirt socket、非 privileged。
- 首次管理员初始化、登录、改密和 Session 撤销。
- root/普通用户免密 sudo，密码/私钥 SSH，Host Key 变化。
- 传统及模块化 libvirt，两台远端 KVM 节点。
- 已有 VM/Pool/网络/Bridge/VLAN 自动发现。
- Linux/Windows VM、ISO、镜像复制、noVNC、串口、快照和克隆。
- NetworkManager、networkd、Netplan、网络失联自动回滚。
- dir/NFS netfs、关机迁移、容器重启任务恢复。

## 故障注入与零残留

覆盖 SSH/节点/容器中断、SQLite 锁、复制中断、哈希不符、XML 失败、重复提交、
并发 VM 修改、Tunnel 中断和媒体吊销。

节点移除后检查进程、unit、cron、临时目录、socket、连接和系统路径，不得存在
Nexora 临时实体；VM、磁盘、Pool、NFS、Bridge 和 VLAN 必须仍存在。

## 未验证项

`shellcheck` 未安装，入口脚本尚未由 shellcheck 验证。当前真实环境已覆盖 Rocky
9.7（RHEL 兼容系，root，libvirt 11.10/QEMU 10.1）、Ubuntu 26.04 LTS（长期
全功能节点，libvirt 12.0/QEMU 10.2）、Debian 13 与 Ubuntu 24.04 LTS（临时
nested KVM）；独立 NFS Server、双 KVM 节点跨节点克隆和完整故障注入尚未验证。

## P7 验证记录（2026-07-31）

| 验证 | 结果 | 说明 |
|---|---|---|
| P7 外围设备/XML 定向 | PASS；9 tests | 关机、跨节点、IOMMU、vfio、占用、realpath、执行前重验 |
| VM 指标失败降级定向 | PASS；4 tests | SSH/执行器异常转换为页面 200 局部降级 |
| `uv run ruff check src tests` | PASS | 无 lint 错误 |
| `uv run ruff format --check src tests` | PASS | 367 files formatted |
| `uv run mypy src` | PASS | 241 source files |
| `uv run pytest -q` | PASS；366 passed，22 skipped | 5 个 Python 3.14 SQLite datetime adapter 警告 |
| Browser QA | PASS | 1280/375px；初始化、IPv6 表单、Host 指标、VM 高级设备；无横向溢出/控制台错误 |
| 状态优先 UI Web 回归 | PASS；38 tests | Dashboard、Host、VM、指标、Guest Agent 与共享代码视图 |
| 状态优先 UI Browser QA | PASS | 1280/375px；4 条全宽横向子系统、操作/XML 默认折叠、无溢出或控制台错误 |
| XML 代码视图 | PASS | 22 行行号、21 个语法 Token、复制按钮和受控横向滚动 |
| `npm run build:assets` / `npm audit --omit=dev` | PASS | 静态资产构建成功；0 vulnerabilities |
| `docker compose build nexora` | PASS | 新镜像 `sha256:24b6d693...64eae` |
| 正式服务部署 | PASS | `0.0.0.0:8002`、healthy、revision 0020、SQLite quick_check ok |
| 正式登录页 Browser QA | PASS | HTTP 登录页正常、1280px 无横向溢出或浏览器错误 |

P7 真实 Rocky 指标、virtiofs、IPv6-only 和双栈启动已执行并通过。PCI 直通未执行：
当前节点 IOMMU group 数量为 0，且没有预绑定 `vfio-pci` 的隔离测试设备；不得通过
修改内核启动参数或绑定随机业务设备规避该硬件门禁。9p 未单独实测，virtiofs 已覆盖
共享目录写入主路径。默认全量中的 24 个 integration skip 仍不得视为远端验证。

## P8 增量验证（2026-08-01）

| 验证 | 结果 | 说明 |
|---|---|---|
| VM 详情生命周期 API | PASS；2 tests | 当前资源版本、状态门禁和强制操作名称确认 |
| React 核心应用 | PASS；13 tests | VM 操作区、任务中心、UEFI 非安全启动及既有核心页面 |
| 存储内部 API | PASS；3 tests | Pool/Volume 创建与生命周期 |
| React 任务内部 API | PASS；4 tests | 列表、详情、CSRF、取消与显式恢复 |
| 媒体库回归 | PASS；1 test | React Shell、内部索引、扫描及受保护内容链路 |
| TypeScript / Ruff / Mypy | PASS | 本批新增 VM、任务和媒体模块定向检查通过 |
| `npm --prefix frontend run build` | PASS | 4818 modules；Ant Design vendor chunk 931.89 kB 警告 |

## 节点只读门禁回滚验证（2026-08-05）

| 验证 | 结果 | 说明 |
|---|---|---|
| 回滚范围 | PASS | 移除 `Host.read_only`、迁移 0023、`ensure_host_writable` 与 13 个 internal 写路由共 40 处拦截；迁移文件删除 |
| Ruff check / format | PASS | `src/nexora/web/internal/` 与 `hosts/models.py` 全部通过 |
| Mypy | PASS | 30 source files，无问题 |
| 数据库迁移测试 | PASS | `tests/test_database.py` 迁移链回到 `20260803_0022` |
| Web 回归 | PASS | `tests/web/` 80 passed |
| 残留检查 | PASS | `rg` 无 `read_only` / `ensure_host_writable` / `host_read_only` 残留 |

## P9-007 操作区与总览增强验证（2026-08-05）

| 验证 | 结果 | 说明 |
|---|---|---|
| 总览扩展 | PASS；1 test | OverviewSummary 新增 vm_paused/vm_stopped/task_pending/storage_pool_total/storage_volume_total |
| VM 列表过滤 | PASS；1 test | `/internal/vms` 按 state/host_id 过滤、未知节点返回空 |
| 后端全量 | PASS | `uv run pytest -q` 426 passed、25 skipped |
| Ruff / Mypy | PASS | 修改的 read_service、core、contracts 定向检查通过 |
| 前端测试 | PASS；20 tests | 含强制操作父元素 `nx-vm-danger-row` 断言与 VM 列表过滤渲染 |
| 前端构建 | PASS | `tsc -b && vite build` 无错误 |

## 存储发现容错修复验证（2026-08-05）

| 验证 | 结果 | 说明 |
|---|---|---|
| 卷名容错解析 | PASS；1 test | `parse_volume_list` 对含 `\xff` 非法 UTF-8 字节卷名改用替换解码，不再抛异常 |
| 坏卷跳过 | PASS；1 test | 单个卷 `vol-dumpxml` 失败时跳过并计入 `StorageDiscoveryResult.warnings`，其他卷正常入库 |
| 后端全量 | PASS | `uv run pytest -q` 428 passed、25 skipped |
| kvm1 生产重扫 | PASS | `host.resource_discovery` succeeded：pools=7, volumes=64, interfaces=36, pci=28, usb=4, storage_warnings=10 |
| kvm1 拓扑恢复 | PASS | 接口资源入库，物理口 enp6s0/enp7s0f0/enp7s0f1 → VLAN/Bridge → vnet → VM 层级就绪 |

## 网络拓扑边按名称解析修复验证（2026-08-05）

| 验证 | 结果 | 说明 |
|---|---|---|
| 名称引用边 | PASS；1 test | master/parent 为接口名时 `_resolve_reference` 按 label 关联，vlan/bridge/vnet/vm 边齐全 |
| 后端全量 | PASS | `uv run pytest -q` 429 passed、25 skipped |
| 前端层级测试 | PASS | physical→vlan→bridge→vnet→vm_nic→vm 逐层断言 |
| kvm1 生产拓扑边 | PASS | `enp7s0f0→enp7s0f0.100(parent)→br_100(bridge_port)→vnet→vm_nic→vm` 完整链路 |

## 网络拓扑标签可读化验证（2026-08-05）

| 验证 | 结果 | 说明 |
|---|---|---|
| 前端测试 | PASS；21 tests | 层级定位与边构建断言通过（含中文关系标签数据） |
| 前端构建 | PASS | `tsc -b && vite build` 无错误 |
| 部署 | PASS | `nexora:latest` healthy，回滚镜像 `nexora:rollback-nettips-20260805T101541Z` 保留 |
| 已知 flaky | 记录 | 全量前端并行时 `previews a VM creation plan`/`legacy VM manage URL` 偶发失败，单独运行均通过，与网络改动无关，待专项排查测试隔离 |

## 节点能力探测工具检测修复验证（2026-08-05）

| 验证 | 结果 | 说明 |
|---|---|---|
| 根因确认 | PASS | `env -- LC_ALL=C command -v <tool>` 中 `command` 为 shell 内建，env 无法执行（rc=127）；无 env 时 `command -v virsh` 返回 `/usr/bin/virsh` |
| 探测修复 | PASS；1 test | 工具探测不再用 env 包装，passwordless 节点 `command -v` 正常（断言命令不含 env） |
| 后端全量 | PASS | `uv run pytest -q` 430 passed、25 skipped |
| ubuntu2604-kvm 生产重探 | PASS | 节点 degraded→ready；tool.virsh/qemu-img/virt-install 等全部 required/optional_missing→normal |
