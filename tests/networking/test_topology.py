import json
from types import SimpleNamespace

import pytest

from nexora.networking.topology import build_network_topology
from nexora.resources.models import ResourceStatus, ResourceType


def test_topology_links_vlan_bridge_vnet_and_vm_nic() -> None:
    host = SimpleNamespace(id="host-1", address="192.0.2.10")
    resources = [
        _interface(2, "eth0", "physical", mtu=1500, flags=["LOWER_UP"]),
        _interface(3, "eth0.100", "vlan", parent=2, master=4, vlan=100, mtu=1500),
        _interface(
            4,
            "br100",
            "bridge",
            addresses=[{"local": "192.0.2.10"}],
            routes=[{"dst": "default", "gateway": "192.0.2.1"}],
            mtu=1500,
        ),
        _interface(5, "vnet0", "vnet", master=4, mtu=1400),
        _vm(),
    ]

    topology = build_network_topology(host, resources)  # type: ignore[arg-type]

    assert {
        ("if:2", "if:3", "parent"),
        ("if:3", "if:4", "bridge_port"),
        ("if:4", "if:5", "bridge_port"),
        ("if:5", "nic:vm-uuid:0", "vm_attachment"),
        ("nic:vm-uuid:0", "vm:vm-uuid", "belongs_to"),
    }.issubset({(item.source, item.target, item.relation) for item in topology.edges})
    management = {item.id for item in topology.nodes if item.management}
    assert {"if:2", "if:3", "if:4", "if:5"}.issubset(management)
    assert any(item.default_route and item.id == "if:4" for item in topology.nodes)
    assert any("mtu_mismatch" in item.warnings for item in topology.edges)
    assert {"up"} == {item.status for item in topology.nodes if item.id.startswith("if:")}
    assert {"running"} == {
        item.status for item in topology.nodes if item.id.startswith(("vm:", "nic:"))
    }


def test_topology_links_by_interface_name_when_ifindex_is_absent() -> None:
    host = SimpleNamespace(id="host-1", address="192.0.2.10")
    resources = [
        _interface(2, "eno1", "physical"),
        _interface(3, "eno1.100", "vlan", parent_name="eno1", master_name="br_100"),
        _interface(4, "br_100", "bridge"),
        _interface(5, "vnet0", "vnet", master_name="br_100"),
        _vm(),
    ]

    topology = build_network_topology(host, resources)  # type: ignore[arg-type]

    assert {
        ("if:2", "if:3", "parent"),
        ("if:3", "if:4", "bridge_port"),
        ("if:4", "if:5", "bridge_port"),
        ("if:5", "nic:vm-uuid:0", "vm_attachment"),
        ("nic:vm-uuid:0", "vm:vm-uuid", "belongs_to"),
    }.issubset({(item.source, item.target, item.relation) for item in topology.edges})


def test_topology_marks_down_physical_interface_and_rejects_bad_json() -> None:
    host = SimpleNamespace(id="host-1", address="node.example.test")
    down = _interface(2, "eth0", "physical", state="DOWN", flags=[])
    topology = build_network_topology(host, [down])  # type: ignore[arg-type]
    assert "down" == topology.nodes[0].status
    assert ("link_down", "no_carrier") == topology.nodes[0].warnings
    down.details_json = "[]"
    with pytest.raises(ValueError, match="details"):
        build_network_topology(host, [down])  # type: ignore[arg-type]


def test_topology_shows_passthrough_pci_network_cards() -> None:
    host = SimpleNamespace(id="host-1", address="192.0.2.10")
    resources = [
        _vm_with_hostdev(),
        _pci("0000:05:00.0", "0x020000", "I211 Gigabit Network Connection"),
        _pci("0000:06:00.0", "0x020000", "I211 Gigabit Network Connection"),
        _pci("0000:03:00.0", "0x030000", "VGA compatible controller"),
    ]

    topology = build_network_topology(host, resources)  # type: ignore[arg-type]

    hostdev_nodes = [node for node in topology.nodes if node.id.startswith("hostdev:")]
    assert 2 == len(hostdev_nodes)
    assert {"0000:05:00.0", "0000:06:00.0"} == {
        node.details["pci_address"] for node in hostdev_nodes
    }
    assert all(node.node_type == "vm_nic" for node in hostdev_nodes)
    assert all(node.details.get("passthrough") is True for node in hostdev_nodes)
    for node in hostdev_nodes:
        assert ("I211" in node.label or node.label.startswith("0000:")) is True
        assert ("hostdev:vm-uuid:0000:05:00.0" == node.id) or (
            "hostdev:vm-uuid:0000:06:00.0" == node.id
        )
    assert {
        ("hostdev:vm-uuid:0000:05:00.0", "vm:vm-uuid", "belongs_to"),
        ("hostdev:vm-uuid:0000:06:00.0", "vm:vm-uuid", "belongs_to"),
    }.issubset({(item.source, item.target, item.relation) for item in topology.edges})


def _interface(
    ifindex: int,
    name: str,
    kind: str,
    *,
    parent: int | None = None,
    master: int | None = None,
    parent_name: str | None = None,
    master_name: str | None = None,
    vlan: int | None = None,
    addresses: list[dict[str, object]] | None = None,
    routes: list[dict[str, object]] | None = None,
    mtu: int = 1500,
    state: str = "UP",
    flags: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        resource_type=ResourceType.HOST_INTERFACE,
        status=ResourceStatus.READ_ONLY,
        native_id=str(ifindex),
        display_name=name,
        details_json=json.dumps(
            {
                "ifindex": ifindex,
                "kind": kind,
                "parent_ifindex": parent_name if parent_name is not None else parent,
                "master_ifindex": master_name if master_name is not None else master,
                "vlan_id": vlan,
                "addresses": addresses or [],
                "routes": routes or [],
                "mtu": mtu,
                "operstate": state,
                "flags": flags if flags is not None else ["LOWER_UP"],
            }
        ),
    )


def _vm() -> SimpleNamespace:
    return SimpleNamespace(
        resource_type=ResourceType.VIRTUAL_MACHINE,
        status=ResourceStatus.MANAGED,
        native_id="vm-uuid",
        display_name="guest",
        details_json=json.dumps(
            {
                "state": "running",
                "interfaces": [
                    {
                        "type": "bridge",
                        "source": "br100",
                        "target": "vnet0",
                        "mac": "52:54:00:12:34:56",
                        "model": "virtio",
                    }
                ],
            }
        ),
    )


def _vm_with_hostdev() -> SimpleNamespace:
    return SimpleNamespace(
        resource_type=ResourceType.VIRTUAL_MACHINE,
        status=ResourceStatus.MANAGED,
        native_id="vm-uuid",
        display_name="guest",
        details_json=json.dumps(
            {
                "state": "running",
                "interfaces": [],
                "host_devices": [
                    {
                        "type": "pci",
                        "mode": "subsystem",
                        "address": {
                            "domain": "0x0000",
                            "bus": "0x05",
                            "slot": "0x00",
                            "function": "0x0",
                        },
                    },
                    {
                        "type": "pci",
                        "mode": "subsystem",
                        "address": {
                            "domain": "0x0000",
                            "bus": "0x06",
                            "slot": "0x00",
                            "function": "0x0",
                        },
                    },
                    {
                        "type": "pci",
                        "mode": "subsystem",
                        "address": {
                            "domain": "0x0000",
                            "bus": "0x03",
                            "slot": "0x00",
                            "function": "0x0",
                        },
                    },
                ],
            }
        ),
    )


def _pci(address: str, device_class: str, product: str) -> SimpleNamespace:
    return SimpleNamespace(
        resource_type=ResourceType.PCI_DEVICE,
        status=ResourceStatus.MANAGED,
        native_id=address,
        display_name=f"pci_{address.replace(':', '_').replace('.', '_')}",
        details_json=json.dumps(
            {
                "address": address,
                "class": device_class,
                "product": product,
                "driver": "vfio-pci",
            }
        ),
    )
