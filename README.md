# <img src="static/nexora-logo.png" alt="Nexora" height="28" /> Nexora

Elegant virtual infrastructure management.

Nexora 是轻量级、无 Agent、单容器、多节点 libvirt/KVM Web 管理平台。
当前项目处于 P0 基础架构阶段。

## 本地开发

要求 Python 3.12–3.14、`uv` 和仅用于构建静态资源的 Node.js 22+：

```bash
cp .env.example .env
npm ci
npm run build:assets
npm --prefix frontend ci
npm --prefix frontend run build
uv sync
NEXORA_DATA_DIR=.data uv run uvicorn nexora.app:create_app --factory
```

先为 `.env` 生成两份独立密钥；开发环境按需设置
`NEXORA_SESSION_COOKIE_SECURE=false`。

健康检查：

```text
GET /live
GET /ready
```

开发规则和当前入口见：

- `AGENTS.md`
- `PROJECT_STATUS.md`
- `ROADMAP.md`
- `docs/README.md`

## 容器开发

容器内应用以 UID/GID `10001` 运行。首次启动前准备持久化目录和媒体目录：

```bash
mkdir -p data /mnt/nexora-library
sudo chown 10001:10001 data
cp .env.example .env
```

为 `.env` 中两个密钥设置独立的高强度随机值，然后运行：

```bash
openssl rand -base64 32
```

`NEXORA_CREDENTIAL_KEY` 必须解码为 32 字节。轮换时递增 active version，并在所有
凭据重新加密完成前通过 `NEXORA_CREDENTIAL_PREVIOUS_KEYS` 保留旧版本。

```bash
docker compose up --build
```

Compose 只启动一个 Nexora 服务，不挂载 KVM、libvirt 或 Docker socket。
React 与 legacy 静态资源均在镜像构建阶段生成，运行镜像不包含 Node.js 或 npm。
通过域名或管理 IP 访问时，还必须将该值加入 `NEXORA_TRUSTED_HOSTS`。

部署、备份、恢复、升级、回滚和排障命令见
[`docs/operations/README.md`](docs/operations/README.md)。
