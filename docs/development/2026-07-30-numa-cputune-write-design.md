# P5-001 NUMA/CPUTune 写入设计

## 目标

在只读展示（NUMA cells、CPU pinning）基础上，支持 NUMA topology 和 CPU
pinning 的安全写入修改，同时保留未知 XML 内容。

## 范围

### 实现

- NUMA cell 创建/修改/删除
- vCPU pinning 设置/清除
- emulator pinning 设置/清除
- auto-placement 切换

### 不实现

- Host Device 直通分配（已有只读展示）
- vsock/watchdog 写入（设备级，风险较低，后续单独实现）
- CPU cache tuning（maxphysaddr 等高级特性）

## 安全模型

### 核心原则

1. **持久化 XML 优先**：只修改 persistent XML，运行中 VM 需重启生效
2. **保留未知内容**：使用局部 XML 变换，不丢失 vendor 扩展和未知元素
3. **拓扑一致性校验**：NUMA cell 的 CPU 和内存必须覆盖所有 vCPU
4. **回滚**：复用现有 VmChangePlan 回滚机制

### 校验规则

- NUMA cell memory 总和不超过 Domain memory
- NUMA cell cpus 不重叠
- vCPU pinning 的 vCPU id 在 0..max_vcpu-1 范围内
- cpuset 格式校验（数字、范围、逗号分隔）
- emulator pinning cpuset 格式校验

## 技术方案

### XML 变换

在 `src/nexora/xml/numa.py` 和 `src/nexora/xml/cputune.py` 中实现：

- `apply_numa_change(document, change)`：增删改 NUMA cell
- `apply_vcpu_pin(document, vcpu, cpuset)`：设置/清除 vcpupin
- `apply_emulator_pin(document, cpuset)`：设置/清除 emulatorpin

### 复用现有流程

- 预览：`_current_persistent` -> 局部变换 -> Diff -> virt-xml-validate
- 确认：10 分钟 TTL + HMAC token
- 执行：`virsh define` + 写后验证 + 回滚
- 验证：`_verified_after_hash` 检查 persistent hash

### 前端

- CPU 配置区增加"NUMA"折叠区域
- 每行显示 cell id、cpus、memory、memAccess
- 支持"添加 Cell"、"编辑 Cell"、"删除 Cell"
- CPU Pinning 表格支持"设置 Pin"、"清除 Pin"

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| NUMA 配置错误导致 VM 无法启动 | virt-xml-validate 预检 + 写后验证 |
| CPU pinning 冲突 | cpuset 不重叠校验 |
| 未知 XML 丢失 | 局部变换 + fingerprint 验证 |
| 并发修改 | ResourceLockStore VM 级锁 |

## 依赖

- 无 schema 变更（复用 VmChangePlan）
- 无新增依赖
- 需要 virt-xml-validate 可用

## 验收条件

- NUMA cell 增删改通过 virt-xml-validate
- vCPU/emulator pinning 设置/清除通过校验
- 未知 XML 元素保留通过 fingerprint 验证
- 真实 Rocky VM 重启后 NUMA topology 正确生效
