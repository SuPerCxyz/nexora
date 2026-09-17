## Purpose

为 Nexora 唯一管理员的初始化和账户改密提供一致、可验证的密码长度要求，同时保留现有认证、哈希、Session 和审计安全边界。

## ADDED Requirements

### Requirement: Administrator password minimum length

系统 SHALL 对管理员初始化和管理员账户改密使用至少 8 个字符、最多 1,024 个字符的密码长度要求；两次输入必须完全一致。低于最小长度或超过最大长度的密码 SHALL 被拒绝，且不得改变现有账户状态。

#### Scenario: Eight-character password is accepted

- **WHEN** 管理员在初始化或账户改密中提交长度恰好为 8 个字符且两次输入一致的密码
- **THEN** 系统接受该密码并继续既有的安全存储和 Session 更新流程

#### Scenario: Short password is rejected

- **WHEN** 管理员在初始化或账户改密中提交少于 8 个字符的密码
- **THEN** 系统拒绝提交并返回明确的最小长度错误，现有账户密码保持不变

#### Scenario: Password confirmation is required

- **WHEN** 管理员提交两次不一致的密码
- **THEN** 系统拒绝提交，即使两次密码都满足长度要求

#### Scenario: Existing authentication protections remain active

- **WHEN** 管理员通过有效的账户改密流程设置符合长度要求的新密码
- **THEN** 系统仍要求当前密码，使用既有哈希存储，新建当前 Session，并撤销其他 Session；密码和 Token 不进入日志或审计明文
