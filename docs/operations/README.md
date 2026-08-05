# Nexora 运维

本目录是 P0 单容器部署与数据恢复的权威操作入口。

- `DEPLOYMENT.md`：首次部署、密钥、TLS 和健康检查。
- `BACKUP_RESTORE.md`：一致备份、校验、恢复和 recovery point。
- `UPGRADE_ROLLBACK.md`：升级顺序与恢复备份式回滚。
- `TROUBLESHOOTING.md`：健康、权限、SQLite、密钥和任务排查。
- `MEDIA_LIBRARY.md`：只读媒体目录挂载边界。

所有命令默认在仓库根目录执行。生产操作先记录当前镜像 tag、备份路径和密钥版本。
不得把 `.env`、凭据主密钥、SSH 私钥或 Session 值粘贴到工单和日志。
