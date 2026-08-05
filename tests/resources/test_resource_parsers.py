import json

from nexora.resources.host_network_parser import parse_host_interfaces
from nexora.resources.libvirt_network_parser import (
    NetworkInfo,
    parse_network_observation,
)
from nexora.resources.models import ResourceStatus, ResourceType
from nexora.resources.node_device_parser import parse_node_device
from nexora.resources.snapshot_parser import parse_snapshot_observation
from nexora.resources.storage_parser import (
    PoolInfo,
    parse_pool_observation,
    parse_volume_list,
    parse_volume_observation,
)

UUID = "11111111-1111-1111-1111-111111111111"


def test_snapshot_parser_uses_domain_and_name_identity() -> None:
    content = (
        b"<domainsnapshot><name>before</name><state>shutoff</state>"
        b"<creationTime>1700000000</creationTime><memory snapshot='no'/>"
        b"<disks><disk name='vda' snapshot='internal'/></disks>"
        b"<domain type='kvm'><name>vm</name></domain></domainsnapshot>"
    )

    result = parse_snapshot_observation(UUID, "before", content, current=True)

    assert [UUID, "before"] == json.loads(result.native_id)
    assert UUID == result.parent_native_id
    assert "no" == result.details["memory"]
    assert result.details["current"] is True
    assert result.details["parent_name"] is None
    assert isinstance(result.details["domain_hash"], str)


def test_storage_parsers_preserve_pool_and_volume_native_identity() -> None:
    pool_xml = f"""\
<pool type="dir"><name>default</name><uuid>{UUID}</uuid>
<capacity unit="bytes">1000</capacity><allocation unit="bytes">100</allocation>
<available unit="bytes">900</available><target><path>/var/lib/libvirt/images</path></target>
</pool>""".encode()
    volume_xml = b"""\
<volume type="file"><name>vm.qcow2</name><key>/images/vm.qcow2</key>
<capacity unit="bytes">1024</capacity><allocation unit="bytes">512</allocation>
<target><path>/images/vm.qcow2</path><format type="qcow2"/></target></volume>"""

    pool = parse_pool_observation(
        UUID,
        pool_xml,
        PoolInfo("running", True, True, True),
    )
    volume = parse_volume_observation(UUID, volume_xml)

    assert ResourceStatus.MANAGED == pool.status
    assert 900 == pool.details["available_bytes"]
    assert [UUID, "/images/vm.qcow2"] == json.loads(volume.native_id)
    assert "qcow2" == volume.details["format"]


def test_pool_configuration_hash_ignores_volatile_capacity_values() -> None:
    first = (
        f"<pool type='dir'><name>default</name><uuid>{UUID}</uuid>"
        "<capacity>1000</capacity><allocation>100</allocation><available>900</available>"
        "<target><path>/images</path></target></pool>"
    ).encode()
    second = first.replace(b">1000<", b">2000<").replace(b">900<", b">1800<")

    first_observation = parse_pool_observation(
        UUID,
        first,
        PoolInfo("running", True, True, True),
    )
    second_observation = parse_pool_observation(
        UUID,
        second,
        PoolInfo("running", True, True, True),
    )

    assert first_observation.persistent_hash == second_observation.persistent_hash


def test_volume_configuration_hash_ignores_only_dynamic_allocation() -> None:
    first = (
        b"<volume type='file'><name>vm.qcow2</name><key>/images/vm.qcow2</key>"
        b"<capacity>1024</capacity><allocation>0</allocation>"
        b"<target><path>/images/vm.qcow2</path><format type='qcow2'/></target></volume>"
    )
    allocation_changed = first.replace(
        b"<allocation>0</allocation>",
        b"<allocation>512</allocation><physical>196616</physical>",
    ).replace(
        b"</target>",
        b"<timestamps><mtime>123.4</mtime></timestamps></target>",
    )
    capacity_changed = first.replace(b"<capacity>1024", b"<capacity>2048")

    base = parse_volume_observation(UUID, first)
    allocated = parse_volume_observation(UUID, allocation_changed)
    resized = parse_volume_observation(UUID, capacity_changed)

    assert base.persistent_hash == allocated.persistent_hash
    assert base.persistent_hash != resized.persistent_hash


def test_volume_list_parser_uses_fixed_header_column_for_names_with_spaces() -> None:
    content = b"""\
 Name                 Path
------------------------------------------------------------------------------
 disk one.qcow2       /images/disk one.qcow2
 second.raw           /images/second.raw
"""

    assert ["disk one.qcow2", "second.raw"] == parse_volume_list(content)


def test_libvirt_network_parser_marks_complex_mode_partial() -> None:
    content = f"""\
<network><name>routed</name><uuid>{UUID}</uuid><forward mode="route"/>
<bridge name="virbr2"/><ip address="192.0.2.1" prefix="24"/></network>""".encode()

    result = parse_network_observation(
        UUID,
        content,
        NetworkInfo(active=True, persistent=True, autostart=False),
    )

    assert ResourceStatus.PARTIALLY_SUPPORTED == result.status
    assert "route" == result.details["forward_mode"]


def test_host_network_parser_discovers_vlan_bridge_relationships() -> None:
    links = json.dumps(
        [
            {
                "ifindex": 2,
                "ifname": "eth0",
                "link_type": "ether",
                "address": "00:11:22:33:44:55",
                "mtu": 1500,
            },
            {
                "ifindex": 3,
                "ifname": "eth0.100",
                "link_index": 2,
                "master": 4,
                "linkinfo": {"info_kind": "vlan", "info_data": {"id": 100}},
                "mtu": 1500,
            },
            {
                "ifindex": 4,
                "ifname": "br100",
                "linkinfo": {"info_kind": "bridge", "info_data": {}},
                "mtu": 1500,
            },
        ]
    ).encode()
    addresses = json.dumps(
        [{"ifindex": 4, "addr_info": [{"family": "inet", "local": "192.0.2.10"}]}]
    ).encode()
    routes = json.dumps([{"dst": "default", "gateway": "192.0.2.1", "dev": "br100"}]).encode()

    observations = parse_host_interfaces(links, addresses, routes, b"[]", b"[]")
    vlan = next(item for item in observations if item.display_name == "eth0.100")
    bridge = next(item for item in observations if item.display_name == "br100")

    assert "2" == vlan.parent_native_id
    assert 100 == vlan.details["vlan_id"]
    assert "192.0.2.10" == bridge.details["addresses"][0]["local"]
    assert "default" == bridge.details["routes"][0]["dst"]


def test_host_network_parser_preserves_vnet_identity_over_tun_kind() -> None:
    links = json.dumps(
        [
            {
                "ifindex": 9,
                "ifname": "vnet0",
                "link_type": "ether",
                "master": 4,
                "linkinfo": {"info_kind": "tun", "info_data": {}},
            }
        ]
    ).encode()
    observations = parse_host_interfaces(links, b"[]", b"[]", b"[]", b"[]")
    assert "vnet" == observations[0].details["kind"]


def test_node_device_parsers_use_stable_pci_and_explicit_usb_identity() -> None:
    pci = b"""\
<device><name>pci_0000_03_00_0</name><driver><name>vfio-pci</name></driver>
<capability type="pci"><class>0x030000</class><domain>0</domain><bus>3</bus>
<slot>0</slot><function>0</function><vendor id="0x10de">NVIDIA</vendor>
<product id="0x1abc">GPU</product><iommuGroup number="12"/></capability></device>"""
    usb = b"""\
<device><name>usb_1_2</name><capability type="usb_device"><bus>1</bus>
<device>2</device><vendor id="0x1234">Vendor</vendor>
<product id="0xabcd">Device</product></capability></device>"""

    pci_result = parse_node_device(pci, ResourceType.PCI_DEVICE)
    usb_result = parse_node_device(usb, ResourceType.USB_DEVICE)

    assert "0000:03:00.0" == pci_result.native_id
    assert "12" == pci_result.details["iommu_group"]
    assert [1, 2, "0x1234", "0xabcd"] == json.loads(usb_result.native_id)
