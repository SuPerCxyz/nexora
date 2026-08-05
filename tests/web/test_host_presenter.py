import json
from types import SimpleNamespace

from nexora.web.internal.host_presenter import host_features, host_hardware, host_network_adapters


def test_host_features_hide_technical_capabilities() -> None:
    capabilities = [
        _capability("tool.virsh", "normal", "/usr/bin/virsh"),
        _capability("libvirt.version", "normal", "libvirt 11"),
        _capability("tool.virt-install", "optional_missing"),
        _capability("tool.ip", "permission_denied"),
    ]

    features = {item.key: item for item in host_features(capabilities)}  # type: ignore[arg-type]

    assert "supported" == features["virtualization"].status
    assert "unsupported" == features["vm_create"].status
    assert "attention" == features["network_discovery"].status
    assert "/usr/bin/virsh" not in str(features.values())


def test_host_features_report_ready_pcie_passthrough_devices() -> None:
    devices = [
        SimpleNamespace(details_json=json.dumps({"iommu_group": "17", "driver": "vfio-pci"})),
        SimpleNamespace(details_json=json.dumps({"iommu_group": "18", "driver": "ixgbe"})),
    ]

    features = {item.key: item for item in host_features([], devices)}  # type: ignore[arg-type]

    assert "supported" == features["pcie_passthrough"].status
    assert "已发现 1 个可直通 PCIe 设备" == features["pcie_passthrough"].description


def test_host_hardware_uses_lscpu_and_nodeinfo_fallbacks() -> None:
    capabilities = [
        _capability("system.uname", "normal", "Linux 6.12.0 x86_64"),
        _capability("system.os_release", "normal", {"pretty_name": "Rocky Linux 9.7"}),
        _capability("system.manufacturer", "normal", "Example Vendor"),
        _capability("system.product_name", "normal", "Example Server"),
        _capability("system.lscpu", "normal", {"model_name": "Example CPU", "logical_cpus": 16}),
        _capability("libvirt.nodeinfo", "normal", {"sockets": 2, "memory_kib": 32768}),
    ]

    hardware = host_hardware(capabilities)  # type: ignore[arg-type]

    assert "Example Server" == hardware.model
    assert "Example CPU" == hardware.cpu_model
    assert 16 == hardware.logical_cpus
    assert 2 == hardware.sockets
    assert 33554432 == hardware.memory_bytes


def test_host_network_adapters_include_mac_and_filter_virtual_links() -> None:
    resources = [
        _interface("eno1", "physical", "00:11:22:33:44:55", routes=[{"dst": "default"}]),
        _interface("veth0", "physical", "00:11:22:33:44:66"),
        _interface("docker0", "physical", "00:11:22:33:44:67"),
        _interface("br0", "bridge", "00:11:22:33:44:77"),
        _interface("br-mgmt", "bridge", "00:11:22:33:44:88", routes=[{"dst": "default"}]),
    ]

    adapters = host_network_adapters(resources)  # type: ignore[arg-type]

    assert ["eno1", "br-mgmt"] == [item.name for item in adapters]
    assert "00:11:22:33:44:55" == adapters[0].mac
    assert adapters[0].management
    assert adapters[1].management


def _capability(key: str, status: str, value: object = None) -> SimpleNamespace:
    return SimpleNamespace(
        capability_key=key,
        status=status,
        value_json=json.dumps(value) if value is not None else None,
    )


def _interface(
    name: str,
    kind: str,
    mac: str,
    *,
    routes: list[dict[str, object]] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        display_name=name,
        details_json=json.dumps(
            {"kind": kind, "mac": mac, "operstate": "UP", "routes": routes or []}
        ),
    )
