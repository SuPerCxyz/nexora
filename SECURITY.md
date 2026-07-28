# Nexora 安全基线与威胁模型

## 信任边界

- 浏览器与 Nexora Web/Session 边界。
- Nexora 容器与 `/data`、`/library` 边界。
- Nexora 与不完全可信远端节点之间的 SSH 边界。
- QEMU 通过媒体 URL 访问 Nexora 的媒体边界。
- 管理员输入与命令、XML、路径、URI 的解释边界。

远端节点可能失陷或返回恶意输出；不得信任命令输出、XML、文件名或设备元数据。

## 主要威胁与控制

| 威胁 | 强制控制 |
|---|---|
| SSH 中间人 | 严格 Host Key、显式首次确认、变化阻断 |
| 凭据泄漏 | AEAD、字段脱敏、密钥外置、最小日志 |
| 命令/参数注入 | typed adapter、统一 quoting、禁 shell fragment |
| XML XXE/炸弹 | 禁 DTD/实体/网络/XInclude，限制尺寸和深度 |
| 路径/符号链接逃逸 | allowlist 根、realpath、原子创建、归属验证 |
| CSRF/Session 劫持 | CSRF、HttpOnly、Secure、SameSite、Session 轮换 |
| XSS | 默认转义、CSP、Diff/日志转义、禁止不可信 HTML |
| WebSocket 劫持 | Origin、Session 和一次性 token 绑定 |
| SSRF/URI 注入 | scheme allowlist、地址验证、禁止 SSH 配置注入 |
| 重复危险操作 | 幂等键、资源锁、外部状态验证 |
| 带外覆盖 | generation/hash、三方 Diff、冲突阻断 |
| 网络失联 | 独立回滚任务、确认期限、无回滚则拒绝 |
| 恶意远端输出 | 输出限额、超时、安全解析、终端转义处理 |
| 审计删除 | 审计不可级联删除、保留资源 tombstone |

## Web 安全

- 所有状态变更包含 CSRF；初始化和登录同样受保护。
- 登录失败按来源和账号限速，避免泄露账号存在性。
- 登录成功和权限变化后轮换 Session ID；改密后撤销旧 Session。
- 响应使用 CSP、`frame-ancestors`、nosniff 和 Referrer-Policy。
- 校验 Host Header；生产明确受信代理和 HTTPS 终止边界。
- Token、密码、私钥、口令、Cookie 和完整 URI query 不进入日志。

## 凭据

- 使用 AES-256-GCM 或 ChaCha20-Poly1305 等 AEAD。
- 每条记录使用随机 nonce，AAD 绑定 host、credential ID 和 schema version。
- `NEXORA_SECRET_KEY` 与 `NEXORA_CREDENTIAL_KEY` 独立。
- 密文保存 key version，支持分批重加密和可恢复轮换。
- 缺少或错误密钥时 fail closed；禁止以空值或临时密钥启动。
- 备份不包含环境主密钥，恢复必须显式提供原密钥。

## 权限与供应链

容器非 root、最小 capabilities、无 privileged、无宿主 socket。远端使用最小 sudo
范围；平台不写 sudoers。依赖锁定，发布生成 SBOM、许可证清单和漏洞扫描结果。

## 审计

认证、Host Key、凭据轮换、危险预检/确认、远端命令摘要、任务状态、资源冲突、
网络回滚和节点移除均写审计。审计只保存脱敏信息，并设置独立保留和备份策略。

## 安全验证

安全相关合并至少覆盖认证、CSRF、Host Key、命令编码、XML、路径、媒体 token、
任务幂等、网络回滚和节点零残留的定向测试。发现秘密时不得在输出中复述。

