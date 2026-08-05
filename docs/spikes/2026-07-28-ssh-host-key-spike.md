# SSH Host Key 流程 Spike

## 结论

首期使用系统 OpenSSH 客户端。`ssh-keyscan` 仅用于未认证的公钥发现，不能自动建立
信任。页面必须展示目标、端口、算法、SHA-256 指纹和历史状态，管理员明确确认后才
把公钥原子写入该节点独立的 `known_hosts` 文件。

## 连接约束

后续 `RemoteExecutor` 必须固定使用：

```text
StrictHostKeyChecking=yes
UserKnownHostsFile=/data/hostkeys/<host-id>.known_hosts
GlobalKnownHostsFile=/dev/null
UpdateHostKeys=no
```

不得使用 `StrictHostKeyChecking=no/accept-new`，不得复用用户主目录默认
`known_hosts`，不得启用 `ProxyCommand`、`LocalCommand` 或环境 SSH 配置。

## 状态机

- `new`：无历史记录，仅允许展示和确认。
- `match`：发现集合与已确认集合完全一致，允许进入认证预检。
- `changed`：任一算法新增、缺失或 key data 不同，阻断连接并展示新旧指纹。

保存使用临时文件、`0600`、fsync 和同目录原子替换。节点移除删除活跃文件，但历史
指纹仍通过不可变审计 tombstone 保存。

## 验证范围

当前自动化测试覆盖目标校验、指纹、变化检测、路径逃逸和原子权限。真实临时 sshd
集成测试需要测试环境提供 `sshd`，未通过自动安装远端或本机软件来伪造该条件。

