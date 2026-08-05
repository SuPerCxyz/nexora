# 故障排查

## 容器不健康

```bash
docker compose ps
docker compose logs --tail=200 nexora
docker inspect nexora --format '{{json .State.Health}}'
```

确认 `/data` 可写、UID/GID 为 `10001`、密钥存在且格式正确。不得把日志中的疑似
Token 或凭据原文复制到外部系统。

## 页面 400 或无法保持登录

- `Invalid host header`：把实际域名/IP 加入 `NEXORA_TRUSTED_HOSTS`。
- HTTP 开发环境无法保持登录：确认是否错误启用了 Secure Cookie；生产必须用 HTTPS。
- 初始化页重复出现：运行 `nexora-ops check`，确认挂载的是预期 `/data`。

## SQLite

```bash
docker compose exec nexora nexora-ops check
docker compose exec nexora ls -ld /data /data/database
```

遇到 lock timeout 先确认只有一个业务容器和一个 Uvicorn worker。不要删除
`-wal`/`-shm` 文件，不要直接复制活动数据库。完整性失败时停止容器并从已校验备份
恢复。

## 凭据无法解密

确认 active key version 与恢复前一致，旧版本密钥仍位于
`NEXORA_CREDENTIAL_PREVIOUS_KEYS`。不要尝试修改数据库密文或猜测 key version。

## 中断任务

容器重启后旧进程的 `running/recovering/cancel_requested` 任务会变为
`interrupted`，不会自动重放。进入任务中心查看 checkpoint；远端状态验证适配器
实现前，不要手工把危险任务改回 `queued`。
