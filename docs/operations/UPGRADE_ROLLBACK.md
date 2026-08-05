# 升级与回滚

## 升级

记录当前 `NEXORA_IMAGE`、凭据 key version 和数据库备份路径。然后：

```bash
docker compose stop nexora
docker compose run --rm nexora nexora-ops backup
docker compose pull nexora
docker compose up -d nexora
docker compose ps
docker compose exec nexora nexora-ops check
```

容器入口自动执行 Alembic upgrade。健康检查和管理员登录均成功前，不清理旧镜像、
升级前备份或 recovery point。

## 回滚

Nexora 不承诺对数据库执行 Alembic downgrade。回滚使用旧镜像和升级前备份：

1. `docker compose stop nexora`。
2. 将 `.env` 的 `NEXORA_IMAGE` 恢复为已记录的旧 tag/digest。
3. 使用旧版本兼容的 `nexora-ops restore` 恢复升级前备份。
4. `docker compose up -d nexora`。
5. 检查 health、SQLite、登录、任务和审计记录。

不得只切回旧镜像并继续使用已被新版本迁移的数据库。若新版本执行了不可逆外部
写操作，还必须按对应 Operation/Task 的验证与补偿说明处理；数据库恢复不会回滚
远端 KVM 资源。
