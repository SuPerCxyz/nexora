# 单容器部署

## 前置条件

- Linux、Docker Engine 和 Compose v2。
- 管理节点不需要 KVM，不挂载 libvirt/Docker socket，不使用 privileged。
- `/data` 对容器 UID/GID `10001` 可写；媒体目录只读。
- 生产环境由 HTTPS 反向代理终止 TLS。

## 初始化

```bash
cp .env.example .env
mkdir -p data /mnt/nexora-library
sudo chown 10001:10001 data
chmod 700 data
```

分别执行两次 `openssl rand -base64 32`，把不同值写入 `.env` 的
`NEXORA_SECRET_KEY` 和 `NEXORA_CREDENTIAL_KEY`。后者解码后必须正好 32 字节。
限制 `.env` 为 `0600`，不要提交版本库。

```bash
chmod 600 .env
docker compose build
docker compose run --rm nexora nexora-ops init
docker compose up -d
docker compose ps
```

## TLS 与 Host

生产环境保持 `NEXORA_SESSION_COOKIE_SECURE=true`。反向代理传入原始 Host，并把域名
加入 `NEXORA_TRUSTED_HOSTS`。只有隔离的 HTTP 开发环境可以显式设为 `false`。

## 验证

```bash
curl --fail http://127.0.0.1:8000/live
curl --fail http://127.0.0.1:8000/ready
docker inspect nexora --format '{{.State.Health.Status}} {{.Config.User}}'
docker compose exec nexora nexora-ops check
```

预期 health 为 `healthy`、用户为 `10001:10001`、SQLite `quick_check` 为 `ok`。
首次访问必须进入管理员初始化页。
