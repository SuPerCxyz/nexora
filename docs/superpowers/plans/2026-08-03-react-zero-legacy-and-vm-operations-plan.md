# React 零旧前端与 VM 操作闭环实施计划

## 阶段 1：契约与迁移护栏

1. 建立通用 JSON 预览与任务响应契约。
2. 为 VM 配置预检/应用增加 internal API。
3. 为存储删除、扩容和删除增加 internal API。
4. 增加禁止业务 Jinja 渲染和 `DOMParser` 的测试。
5. React 切换到 JSON API 后移除对应旧路由与模板。

## 阶段 2：节点优先 VM 创建

1. 创建选项按节点返回 Pool、Volume、网络和 ISO。
2. 创建页改为节点优先和三种系统盘来源。
3. 扩展创建计划支持空白磁盘参数。
4. 任务先无覆盖创建 Volume，再定义并验证 VM。
5. 补充失败补偿、恢复、碰撞和引用测试。

## 阶段 3：已有后端能力 React 化

1. 快照创建、删除和恢复改为 internal JSON API。
2. VM 详情增加快照操作与统一确认弹窗。
3. 克隆/关机迁移改为 internal JSON API。
4. VM 详情增加目标节点、Pool、名称和源清理确认。
5. VM 自动启动 internal API 与详情操作接通。

## 阶段 4：新增 VM 管理能力

1. 设计 VM 删除持久化计划、任务和清理清单。
2. 实现默认 undefine 与可选磁盘/NVRAM 删除。
3. 设计并实现关机 VM 重命名计划与任务。
4. 实现网卡 attach/detach/edit XML 变换和校验。
5. 接入同节点网络候选、MAC 唯一性和 live/config 门禁。

## 阶段 5：存储与高级配置零旧前端

1. 迁移 CPU、内存、磁盘、光驱预检和应用。
2. 迁移 NUMA、CPU Pinning、高级设备和共享目录。
3. 迁移平台 ISO/缓存 ISO 操作。
4. 迁移 Pool 删除与 Volume 扩容/删除 UI。
5. 删除 HTML 预览解析和全部业务模板。

## 阶段 6：验证与部署

1. 运行每个服务、任务、API 和 React 定向测试。
2. 运行 Ruff、格式、Mypy、Pytest 全量门禁。
3. 运行 React typecheck/test/build/audit 和 legacy audit。
4. 对全部产品路由执行四断点 Browser QA。
5. 使用 Rocky 隔离资源执行真实写入与清理验证。
6. 更新状态、路线图、测试和变更文档。
7. 创建一致备份和回滚镜像后部署到 `0.0.0.0:8002`。

## 完成定义

- 没有可达业务 Jinja 页面或 HTML 预览响应。
- React 覆盖旧功能和新增七项功能的完整操作流程。
- 所有危险写操作具备预检、Diff、确认、版本复核、锁、验证和必要回滚。
- 自动化、真实集成、Browser QA 和运行时安全检查全部有通过证据。
