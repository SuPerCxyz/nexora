from nexora.resources.domain_parser import parse_domain_observation
from nexora.resources.models import ResourceStatus

DOMAIN_XML = b"""\
<domain type="kvm">
  <name>existing-vm</name>
  <uuid>11111111-1111-1111-1111-111111111111</uuid>
  <metadata><vendor:opaque xmlns:vendor="urn:vendor">keep</vendor:opaque></metadata>
  <memory unit="KiB">2097152</memory>
  <vcpu current="2">4</vcpu>
  <devices>
    <disk type="file" device="disk"><source file="/var/lib/libvirt/images/vm.qcow2"/>
      <target dev="vda" bus="virtio"/></disk>
    <interface type="bridge"><mac address="52:54:00:12:34:56"/>
      <source bridge="br0"/><target dev="vnet0"/><model type="virtio"/></interface>
  </devices>
</domain>
"""


def test_domain_parser_extracts_bounded_summary_and_preserves_xml() -> None:
    observation = parse_domain_observation(
        "11111111-1111-1111-1111-111111111111",
        DOMAIN_XML,
        None,
        state="shut off",
        autostart=True,
    )

    assert "existing-vm" == observation.display_name
    assert ResourceStatus.MANAGED == observation.status
    assert 2 == observation.details["current_vcpus"]
    assert 4 == observation.details["maximum_vcpus"]
    assert 2_097_152 == observation.details["memory_kib"]
    assert "/var/lib/libvirt/images/vm.qcow2" == observation.details["disks"][0]["source"]
    assert "br0" == observation.details["interfaces"][0]["source"]
    assert b"vendor:opaque" in observation.documents["persistent_xml"]


def test_live_only_domain_is_marked_transient() -> None:
    observation = parse_domain_observation(
        "11111111-1111-1111-1111-111111111111",
        None,
        DOMAIN_XML,
        state="running",
        autostart=False,
    )

    assert ResourceStatus.TRANSIENT == observation.status
    assert observation.persistent_hash is None
    assert observation.live_hash is not None
