# VM 实时性能监控设计

## 目标与方案选择

VM 详情页打开时通过 HTMX 采样实时指标，不把高频数据写入 SQLite。方案比较：

1. 单 worker 内有界差分缓存：符合当前进程模型，采用。
2. 浏览器回传上次计数器：输入可篡改且跨标签页不一致，不采用。
3. 每次采样写 SQLite：产生高频写竞争，不采用；24 小时低频历史另行设计。

## 数据源与计算

统一经 `RemoteExecutor` 执行：

```text
virsh -c <uri> domstats <uuid>
  --state --cpu-total --balloon --block --interface
```

解析 `key=value`，限制总行数、key/value 长度和设备计数。页面只显示聚合值：

- CPU：`delta(cpu.time ns) / delta(monotonic ns) * 100`，允许超过 100%。
- 内存：balloon current、maximum、rss，单位 KiB。
- 磁盘：所有 block 的读写 bytes 差分速率。
- 网络：所有 interface 的收发 bytes 差分速率。
- 状态：domstats state code 的稳定映射。

路径、设备源和未知字段不进入页面。计数器下降、时间异常或首次采样时速率显示为待采样。

## 缓存边界

采样器以 `host_id + VM UUID` 为键，进程锁保护，最多 2,000 项，15 分钟未访问清理。
缓存只保存单调时间与聚合计数器，不持久化、不包含凭据。容器重启后首次采样自然重置。

## Web 与错误

认证后的 VM 详情页使用 HTMX 首次加载并每 5 秒刷新性能卡片。路由重新验证
host/domain 作用域；SSH、libvirt、超时或不完整输出只返回局部“暂不可用”，不影响
整个详情页。所有数值服务端格式化，技术值使用等宽字体。

## 验收

- 单元覆盖解析上限、聚合、首次采样、速率、计数器回退和缓存上限。
- Web 覆盖认证、节点作用域、成功和远端失败局部响应。
- Rocky 运行中 VM 连续采样两次，验证状态、CPU/内存及非负速率。
- Browser QA 覆盖 1280px 与 375px，无溢出、控制台错误或页面级失败。
