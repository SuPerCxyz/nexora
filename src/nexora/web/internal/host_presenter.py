"""User-facing host hardware, feature, and network summaries."""

import json
from dataclasses import dataclass

from nexora.hosts.models import HostCapability
from nexora.resources.models import ResourceIndex
from nexora.web.internal.contracts import (
    HostFeatureSummary,
    HostHardwareSummary,
    HostNetworkAdapterSummary,
)


@dataclass(frozen=True)
class FeatureDefinition:
    key: str
    name: str
    description: str
    requirements: tuple[str, ...]


FEATURES = (
    FeatureDefinition(
        "virtualization",
        "虚拟机管理",
        "查看并控制 libvirt 虚拟机",
        ("tool.virsh", "libvirt.version"),
    ),
    FeatureDefinition(
        "vm_create", "创建虚拟机", "通过标准安装流程创建虚拟机", ("tool.virt-install",)
    ),
    FeatureDefinition(
        "advanced_config",
        "高级配置",
        "安全修改并校验虚拟机 XML",
        ("tool.virt-xml", "tool.virt-xml-validate"),
    ),
    FeatureDefinition(
        "image_management", "镜像管理", "检查、转换和扩展磁盘镜像", ("tool.qemu-img",)
    ),
    FeatureDefinition("network_discovery", "网络发现", "读取接口、地址和路由信息", ("tool.ip",)),
    FeatureDefinition(
        "bridge_vlan",
        "Bridge 与 VLAN",
        "发现和配置 Linux Bridge/VLAN",
        ("tool.ip", "tool.bridge"),
    ),
    FeatureDefinition(
        "network_manager",
        "NetworkManager",
        "使用 NetworkManager 管理网络",
        ("tool.nmcli",),
    ),
    FeatureDefinition(
        "systemd_networkd",
        "systemd-networkd",
        "识别 systemd-networkd 配置",
        ("tool.networkctl",),
    ),
    FeatureDefinition("netplan", "Netplan", "识别 Ubuntu Netplan 配置", ("tool.netplan",)),
    FeatureDefinition("nfs_storage", "NFS 存储", "挂载并管理 NFS 存储池", ("tool.mount.nfs",)),
    FeatureDefinition(
        "open_vswitch", "Open vSwitch", "发现 Open vSwitch 网络", ("tool.ovs-vsctl",)
    ),
)


def host_features(
    capabilities: list[HostCapability],
    pci_devices: list[ResourceIndex] | None = None,
) -> list[HostFeatureSummary]:
    statuses = {item.capability_key: item.status for item in capabilities}
    features = [
        HostFeatureSummary(
            key=feature.key,
            name=feature.name,
            status=_feature_status(statuses, feature.requirements),
            description=feature.description,
        )
        for feature in FEATURES
    ]
    features.insert(3, _pcie_passthrough_feature(pci_devices))
    return features


def _pcie_passthrough_feature(
    pci_devices: list[ResourceIndex] | None,
) -> HostFeatureSummary:
    if pci_devices is None:
        status, description = "attention", "等待 PCI 设备能力扫描"
    else:
        details = [_resource_details(item) for item in pci_devices]
        iommu_devices = [item for item in details if _text(item.get("iommu_group"))]
        ready_devices = [item for item in iommu_devices if item.get("driver") == "vfio-pci"]
        if ready_devices:
            status = "supported"
            description = f"已发现 {len(ready_devices)} 个可直通 PCIe 设备"
        elif iommu_devices:
            status = "attention"
            description = "支持 IOMMU，但暂无已绑定 vfio-pci 的设备"
        else:
            status = "unsupported"
            description = "未发现可用 IOMMU Group"
    return HostFeatureSummary(
        key="pcie_passthrough",
        name="PCIe 设备直通",
        status=status,
        description=description,
    )


def _feature_status(statuses: dict[str, str], requirements: tuple[str, ...]) -> str:
    values = [statuses.get(key) for key in requirements]
    if all(value == "normal" for value in values):
        return "supported"
    if any(value in {None, "unknown", "permission_denied"} for value in values):
        return "attention"
    return "unsupported"


def host_hardware(capabilities: list[HostCapability]) -> HostHardwareSummary:
    values = {item.capability_key: _value(item) for item in capabilities}
    os_release = _mapping(values.get("system.os_release"))
    lscpu = _mapping(values.get("system.lscpu"))
    nodeinfo = _mapping(values.get("libvirt.nodeinfo"))
    kernel, uname_architecture = _uname(values.get("system.uname"))
    memory_kib = _integer(nodeinfo.get("memory_kib"))
    return HostHardwareSummary(
        manufacturer=_text(values.get("system.manufacturer")),
        model=_text(values.get("system.product_name")),
        os_name=_os_name(os_release),
        kernel=kernel,
        architecture=_text(lscpu.get("architecture")) or uname_architecture,
        cpu_model=_text(lscpu.get("model_name")) or _text(nodeinfo.get("cpu_model")),
        logical_cpus=_integer(lscpu.get("logical_cpus")) or _integer(nodeinfo.get("cpus")),
        sockets=_integer(lscpu.get("sockets")) or _integer(nodeinfo.get("sockets")),
        cores_per_socket=_integer(lscpu.get("cores_per_socket"))
        or _integer(nodeinfo.get("cores_per_socket")),
        threads_per_core=_integer(lscpu.get("threads_per_core"))
        or _integer(nodeinfo.get("threads_per_core")),
        numa_nodes=_integer(lscpu.get("numa_nodes")) or _integer(nodeinfo.get("numa_cells")),
        memory_bytes=memory_kib * 1024 if memory_kib is not None else None,
    )


def host_network_adapters(resources: list[ResourceIndex]) -> list[HostNetworkAdapterSummary]:
    adapters: list[HostNetworkAdapterSummary] = []
    for resource in resources:
        details = _resource_details(resource)
        name = resource.display_name
        kind = _text(details.get("kind")) or "unknown"
        management = _management_interface(details)
        if name == "lo" or (not management and _is_virtual_adapter(name, kind)):
            continue
        adapters.append(
            HostNetworkAdapterSummary(
                name=name,
                mac=_text(details.get("mac")),
                kind=kind,
                state=(_text(details.get("operstate")) or "unknown").lower(),
                management=management,
            )
        )
    return adapters


def _is_virtual_adapter(name: str, kind: str) -> bool:
    if kind in {"loopback", "veth", "vnet", "tap", "bridge"}:
        return True
    return name.startswith(("veth", "vnet", "tap", "docker", "virbr", "br-"))


def _value(item: HostCapability) -> object:
    if item.value_json is None:
        return None
    try:
        return json.loads(item.value_json)
    except json.JSONDecodeError:
        return None


def _resource_details(resource: ResourceIndex) -> dict[str, object]:
    try:
        value = json.loads(resource.details_json)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _management_interface(details: dict[str, object]) -> bool:
    routes = details.get("routes")
    return isinstance(routes, list) and any(
        isinstance(route, dict) and route.get("dst") in {"default", "0.0.0.0/0", "::/0"}
        for route in routes
    )


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and 0 < len(value.strip()) <= 512 else None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _uname(value: object) -> tuple[str | None, str | None]:
    parts = value.split() if isinstance(value, str) else []
    return (parts[1] if len(parts) >= 2 else None, parts[-1] if len(parts) >= 3 else None)


def _os_name(values: dict[str, object]) -> str | None:
    pretty = _text(values.get("pretty_name"))
    if pretty is not None:
        return pretty
    name = _text(values.get("name"))
    version = _text(values.get("version_id"))
    return " ".join(item for item in (name, version) if item) or None
