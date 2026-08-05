# 备份与恢复

## 备份内容

`nexora-ops backup` 使用 SQLite online backup API，不直接复制活动 WAL 文件。归档
包含数据库、密文凭据、Host Key、审计、任务输出、操作和进度目录。`runtime`、
`console`、`cache`、旧备份与 recovery point 不递归归档。

主凭据密钥和 `.env` 不在归档中，必须通过独立安全渠道保存。没有原
`NEXORA_CREDENTIAL_KEY` 时，恢复后的密文不可用。

## 创建与检查

在线备份的数据库一致，其他文件为逐文件快照。升级或灾备基线建议停机：

```bash
docker compose stop nexora
docker compose run --rm nexora nexora-ops backup
docker compose up -d
```

命令输出归档绝对路径，默认位于 `/data/backups`。目标已存在或位于被归档目录时
命令拒绝覆盖。归档权限为 `0600`。

## 恢复

恢复是明确的破坏性操作，必须先停止服务：

```bash
docker compose stop nexora
docker compose run --rm nexora nexora-ops restore \
  /data/backups/nexora-YYYYMMDDTHHMMSSZ.tar.gz \
  --confirm-stopped --replace-existing-data
docker compose up -d
docker compose exec nexora nexora-ops check
```

恢复先拒绝路径穿越、链接、设备文件、重复或异常成员，再校验 manifest、数据库
SHA-256 和 SQLite `quick_check`。被替换数据移动到
`/data/recovery/pre-restore-<timestamp>-<id>`，不会立即删除。

确认新数据和登录正常后，管理员再按保留策略处理 recovery point。恢复失败时不要
反复执行；保留归档、recovery 目录和日志后进入排障。
