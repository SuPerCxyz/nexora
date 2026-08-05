# 平台媒体目录

主机目录通过 Compose 只读挂载：

```yaml
volumes:
  - "${NEXORA_LIBRARY_HOST_PATH:-/mnt/nexora-library}:/library:ro"
```

建议结构：

```text
/mnt/nexora-library/
├── iso/{linux,windows,drivers}/
└── images/{linux,windows,cloud}/
```

容器 UID `10001` 需要目录遍历和文件读取权限，不需要写权限。不得把 SSH 私钥、
凭据、备份或其他敏感文件放入媒体目录。

P0 仅固化挂载边界；媒体索引、HTTP Range ISO 服务和镜像复制在 P3 实现。删除媒体
索引不会获得删除原文件的权限，平台也不得扫描 `/library` 之外的文件系统。
