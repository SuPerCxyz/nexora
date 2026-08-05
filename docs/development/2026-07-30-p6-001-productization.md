# P6-001 产品化与兼容验证

## 发行版兼容矩阵

| 发行版 | 版本 | 架构 | 接入 | 发现 | VM 操作 | 克隆 | 验证日期 |
|---|---|---|---|---|---|---|---|
| Rocky Linux | 9.7 | x86_64 | PASS | PASS | PASS | PASS | 2026-07-30 |
| Ubuntu | 26.04 LTS | x86_64 | PASS | PASS | PASS | PASS | 2026-07-30 |
| Ubuntu | 24.04 LTS | x86_64 | PASS | PASS | - | - | 2026-07-29 |
| Debian | 13 | x86_64 | PASS | PASS | - | - | 2026-07-29 |

Rocky 9.7 等同 RHEL 系（CentOS/AlmaLinux/RHEL）。

## SSH 认证矩阵

| 认证方式 | 用户 | sudo | 验证 |
|---|---|---|---|
| 私钥 | root | 不需要 | PASS |
| 私钥 | 普通用户 | 免密 sudo | PASS |
| 密码 | 普通用户 | 免密 sudo | PASS |
| 加密私钥+口令 | root | 不需要 | PASS |

## libvirt 模式矩阵

| 模式 | 发行版 | 验证 |
|---|---|---|
| 传统 libvirtd | Rocky 9.7 | PASS |
| 模块化 daemon | Rocky 9.7 | PASS |
| 传统 libvirtd | Ubuntu 26.04 | PASS |

## 安全验证

- AES-256-GCM 凭据加密：PASS
- SSH Host Key 严格校验+变化阻断：PASS
- XXE/DOCTYPE/XInclude 禁用：PASS
- CSRF + 限速 + 可信 Host：PASS
- 审计脱敏：PASS
- 节点移除零残留：PASS
- 跨节点克隆零残留：PASS

## 性能验证

- VM domstats 实时采样：PASS
- 低频历史存储（24h/240 采样）：已实现
- 任务恢复与崩溃识别：PASS

## 供应链

- npm audit：0 vulnerabilities
- Ruff + mypy strict：229 source files PASS
- 单容器：非 root、非 privileged、0 devices

## aarch64

架构探测已支持（domcapabilities），但缺少真实 aarch64 节点验证。
