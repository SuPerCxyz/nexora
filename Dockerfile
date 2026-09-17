# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS frontend

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY scripts/build-assets.mjs ./scripts/build-assets.mjs
COPY static/nexora-icon.svg ./static/nexora-icon.svg
RUN npm run build:assets

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEXORA_PROJECT_ROOT=/app \
    NEXORA_DATA_DIR=/data \
    NEXORA_LIBRARY_DIR=/library

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        libvirt-clients \
        openssh-client \
        openssl \
        qemu-utils \
        tini \
        virtinst \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 nexora \
    && useradd --uid 10001 --gid nexora --home-dir /app --shell /usr/sbin/nologin nexora \
    && install -d -o nexora -g nexora -m 0700 /data \
    && install -d -o root -g root -m 0755 /library

WORKDIR /app

COPY --from=builder --chown=nexora:nexora /app/.venv /app/.venv
COPY --chown=nexora:nexora src ./src
COPY --chown=nexora:nexora alembic ./alembic
COPY --chown=nexora:nexora alembic.ini ./
COPY --chown=nexora:nexora static ./static
COPY --from=frontend --chown=nexora:nexora /app/static/vendor ./static/vendor
COPY --from=frontend --chown=nexora:nexora /app/static/app ./static/app
COPY --chown=nexora:nexora templates ./templates
COPY --chmod=0755 scripts/entrypoint.sh /usr/local/bin/nexora-entrypoint

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", \
         "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"]

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/nexora-entrypoint"]
CMD ["uvicorn", "nexora.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
