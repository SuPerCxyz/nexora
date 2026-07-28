# Nexora Roadmap

状态：`TODO`、`ANALYZING`、`IN_PROGRESS`、`BLOCKED`、`REVIEW`、`DONE`、`DEFERRED`。

## P0：基础架构

| ID | 标题 | 状态 | 优先级 | 依赖 | 验收条件 | 涉及文件 | 测试要求 | 完成日期/备注 |
|---|---|---|---|---|---|---|---|---|
| P0-001 | 文档与架构基线 | DONE | 最高 | 无 | 权威文档、ADR、威胁模型和恢复入口落盘 | 根文档、`docs/` | 链接/占位/结构检查 | 2026-07-28 |
| P0-002 | Python 项目骨架 | TODO | 最高 | P0-001 | FastAPI 可启动，目录边界确定 | `pyproject.toml`, `src/`, `tests/` | 启动/导入测试 | 未开始 |
| P0-003 | 单容器运行骨架 | TODO | 最高 | P0-002 | Tini、单 worker、非 root、healthcheck | Docker/Compose/entrypoint | 构建与无 KVM 启动 | 未开始 |
| P0-004 | SQLite 与 Alembic | TODO | 最高 | P0-002 | WAL、FK、超时、迁移和统一 Session | `db/`, `alembic/` | pragma/迁移/锁测试 | 未开始 |
| P0-005 | 单管理员认证 | TODO | 最高 | P0-004 | 初始化、登录、改密、Session 撤销 | `auth/`, `web/` | 认证/CSRF/限速 | 未开始 |
| P0-006 | 凭据加密 | TODO | 最高 | P0-004 | AEAD、AAD、key version、fail closed | `security/` | 加密/篡改/轮换 | 未开始 |
| P0-007 | SSH Host Key 流程 Spike | TODO | 最高 | P0-002 | 首次确认、历史显示、变化阻断 | `docs/spikes/`, `remote/` | 临时 sshd 集成测试 | 未开始 |
| P0-008 | RemoteExecutor | TODO | 最高 | P0-006,P0-007 | typed adapter、超时、限额、取消、审计 | `remote/` | 注入/超时/脱敏 | 未开始 |
| P0-009 | 任务 lease Spike | TODO | 最高 | P0-004 | 原子领取、续租、崩溃识别 | `docs/spikes/`, `tasks/` | 并发/重启/锁测试 | 未开始 |
| P0-010 | 持久化任务系统 | TODO | 最高 | P0-008,P0-009 | 步骤、心跳、检查点、恢复和取消 | `tasks/`, `web/` | 状态机/恢复测试 | 未开始 |
| P0-011 | Tabler 页面骨架 | TODO | 高 | P0-005 | 浅色主题、导航、技术字体和错误处理 | `templates/`, `static/` | 页面/可访问性冒烟 | 未开始 |
| P0-012 | XML 保留 Spike | TODO | 最高 | P0-002 | 安全解析、局部修改、规范化 hash | `docs/spikes/`, `xml/` | 未知元素/XXE/Diff | 未开始 |
| P0-013 | P0 部署运维文档 | TODO | 高 | P0-003,P0-010 | 部署、升级、备份、恢复、回滚、排障 | `docs/operations/` | 文档命令演练 | 未开始 |

## 后续阶段

| ID | 标题 | 状态 | 依赖 | 核心验收 |
|---|---|---|---|---|
| P1-001 | 节点接入与能力探测 | TODO | P0 | Host Key 确认后只读探测 |
| P1-002 | 全量资源发现与索引 | TODO | P1-001 | 已有资源无需导入 |
| P1-003 | 带外变更与零残留移除 | TODO | P1-002 | 冲突阻断；业务资源保留 |
| P2-001 | Cockpit Machines VM 基线 | TODO | P1 | 创建、生命周期、设备、控制台 |
| P3-001 | 媒体 Range 与镜像复制 | TODO | P1 | 流式、校验、恢复、吊销 |
| P3-002 | dir 与 NFS netfs | TODO | P1 | 不修改 fstab，不删除业务内容 |
| P4-001 | 网络只读发现与拓扑 | TODO | P1 | 多后端识别和关系图 |
| P4-002 | Bridge/VLAN 安全写入 | TODO | P4-001 | 独立回滚和确认期限 |
| P5-001 | 高级 VM/XML 配置 | TODO | P2 | 局部修改且保留未知内容 |
| P5-002 | 克隆与关机迁移 | TODO | P2,P3 | 文件复制、校验、源端保留 |
| P6-001 | 产品化与兼容验证 | TODO | P1-P5 | 发行版、aarch64、安全、性能 |

详细阶段范围以 `docs/product/SCOPE.md` 为准。开始任务时将对应行改为
`ANALYZING` 或 `IN_PROGRESS`，结束时填写准确日期与结果。

