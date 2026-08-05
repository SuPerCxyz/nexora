# VM 创建网络选择设计

## 范围

在 managed Volume 导入创建基础上，可选添加一张 VirtIO 网卡。支持：

- 不添加网卡。
- 同节点已发现的 Linux Bridge。
- 同节点 active、persistent、managed 的 libvirt NAT/isolated Network。

本切片不创建、修改或删除 Bridge、VLAN、libvirt Network、DHCP、IP 或路由，不接受
页面输入网络名称、MAC、XML、脚本或命令。

## 方案

采用 ResourceIndex 结构化选择。仅支持 libvirt Network 会遗漏已有 Bridge；在创建
向导内同时写宿主机网络则跨入自动回滚高风险域，均不采用。

创建契约保存 network kind、resource ID、native ID、generation 和对应 hash。页面
只提交 resource ID；服务端从索引构造完整契约。预览与执行前刷新目标网络类型：

- Bridge：刷新 HOST_INTERFACE，验证 ifindex、ifname、kind=bridge 和 live hash。
- libvirt Network：刷新 LIBVIRT_NETWORK，验证 UUID、名称、active、persistent、
  managed 和 persistent hash。

资源消失、改名、hash 变化、类型变化或跨节点时阻断。网络资源只被引用而不被修改，
不增加网络写锁；任务仍持有 Volume→VM UUID 双锁。

## XML 与验证

Bridge 生成：

```xml
<interface type="bridge">
  <source bridge="br0"/>
  <model type="virtio"/>
</interface>
```

libvirt Network 生成 `type=network` 与权威 network name。MAC 由 libvirt 生成，写后
验证接口 type、source、model=virtio；不要求 XML byte-for-byte 相同。

## 验收

- 单元：三种模式、跨节点、Bridge kind、Network active/hash、XML 参数安全。
- Web：仅显示符合条件的同节点网络，不存在自由文本网络字段。
- Rocky：使用现有测试 Bridge 或 libvirt Network 定义 VM，验证生成 MAC、启动、
  网络资源保持不变，并精确清理 VM/Volume。
