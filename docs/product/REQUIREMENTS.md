# Nexora 产品需求基线

## 产品定义

- 名称：Nexora
- 标语：Elegant virtual infrastructure management.
- 定位：简洁优雅的多节点虚拟化管理平台。
- 形态：轻量级、无 Agent、单容器、多节点 libvirt/KVM Web 平台。
- 参考：Cockpit Machines 和 WebVirtCloud 仅用于功能、交互和兼容性研究。

Nexora 不替代 OpenStack、OpenNebula、CloudStack、Proxmox 或 vCenter。

## 技术栈

- Python 3.12 或项目锁定的更新稳定版本
- FastAPI、Starlette、Uvicorn 和同源内部 Session API
- React、TypeScript、Vite、Ant Design 6 和经安全审计的客户端路由方案
- Jinja2 仅保留为服务端 Shell/过渡响应实现，不承载可导航产品页面
- SQLAlchemy 2、Alembic、SQLite
- lxml、libvirt 客户端、OpenSSH 客户端
- noVNC、websockify、CodeMirror 6、xterm.js、Cytoscape.js
- pytest、Ruff、mypy 或 pyright

运行时禁止 Django、Node.js 服务、Redis、Celery、RabbitMQ、Kafka和外部数据库。
Node.js 只可在镜像构建阶段编译本地静态资源。

## 核心能力

- 单管理员初始化、登录、设置和登录历史。
- 通过 SSH 添加多台 Linux KVM/libvirt 节点并确认 Host Key。
- 只读预检节点能力，不自动安装软件或修改安全策略。
- 自动发现已有 VM、快照、存储、网络、Bridge、VLAN 和设备。
- 已有资源与 Nexora 创建资源使用同一套管理逻辑。
- 检测带外修改，写入前执行版本比较和 Diff 确认。
- 覆盖 Cockpit Machines 的核心 KVM 虚拟机管理范围。
- 提供结构化高级配置，同时提供安全 XML、校验与 Diff。
- 提供平台媒体库、ISO Range 服务和镜像复制。
- 提供 dir 与 NFS netfs 可写存储；其他类型只读发现。
- 提供 Linux Bridge 与 802.1Q VLAN 安全写入和自动回滚。
- 提供 noVNC、串口、快照、克隆和关机迁移。
- 提供持久化任务、步骤、进度、取消、恢复和审计。

## 数据与资源原则

- `/data` 保存数据库、凭据密文、任务、审计、缓存、备份和运行状态。
- `/library` 只读挂载 ISO、qcow2 和 raw 媒体。
- 删除媒体索引不得删除媒体文件。
- 远端实际状态是业务资源权威数据源。
- SQLite 不得成为 VM、网络或存储配置的唯一副本。
- 不支持修改的现有资源仍须展示并标记能力状态。

## 危险操作原则

危险操作必须包含：

1. 重新读取当前状态。
2. 能力、引用和权限预检查。
3. 目标配置及资源差异预览。
4. 风险说明和显式确认。
5. 幂等任务执行。
6. 应用后重新读取并验证。
7. 审计记录。
8. 可行时自动补偿或回滚。

VM 删除默认仅 undefine。磁盘、NVRAM、源端迁移资源等必须逐项选择并二次确认。

## 页面与体验

- React 页面支持客户端路由、刷新和深链接；FastAPI 仍是唯一业务服务。
- 默认浅亮、低饱和、浅边框和小圆角；默认不使用装饰性阴影。
- 全站颜色来自固定语义 Design Token；禁止渐变、玻璃拟态、霓虹和发光效果。
- 技术字段统一等宽字体，并提供全局等宽字体模式。
- 状态不得只依赖颜色；基础目标为 WCAG 2.1 AA。
- 静态资源本地打包，运行时不依赖公共 CDN。
