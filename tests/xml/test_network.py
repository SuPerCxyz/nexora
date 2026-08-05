import pytest

from nexora.xml.document import LibvirtXmlDocument
from nexora.xml.network import (
    InterfaceAttachChange,
    InterfaceDetachChange,
    InterfaceUpdateChange,
    NetworkConfigError,
    apply_interface_attach,
    apply_interface_detach,
    apply_interface_update,
    verify_interface_attach_result,
)

DOMAIN = b"""\
<domain type="kvm">
  <name>vm</name>
  <uuid>11111111-1111-1111-1111-111111111111</uuid>
  <devices>
    <interface type="network">
      <mac address="52:54:00:aa:bb:cc"/>
      <source network="default"/>
      <model type="virtio"/>
    </interface>
    <mystery keep="yes"/>
  </devices>
</domain>"""


def test_attach_allocates_interface_and_preserves_unknown_devices() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    apply_interface_attach(
        document,
        InterfaceAttachChange("bridge", "br0", "virtio", "52:54:00:aa:bb:dd"),
    )

    interface = document.root.xpath("./devices/interface[source/@bridge='br0']")[0]
    assert "bridge" == interface.get("type")
    assert "52:54:00:aa:bb:dd" == interface.find("mac").get("address")  # type: ignore[union-attr]
    assert "yes" == document.root.find("./devices/mystery").get("keep")  # type: ignore[union-attr]
    assert "52:54:00:aa:bb:cc" == document.root.xpath(  # type: ignore[union-attr]
        "./devices/interface/source[@network='default']/.."
    )[0].find("mac").get("address")


def test_attach_rejects_duplicate_mac_and_source() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    with pytest.raises(NetworkConfigError, match="MAC"):
        apply_interface_attach(
            document,
            InterfaceAttachChange("bridge", "br1", "virtio", "52:54:00:aa:bb:cc"),
        )
    with pytest.raises(NetworkConfigError, match="source"):
        apply_interface_attach(
            document,
            InterfaceAttachChange("network", "default", "virtio"),
        )


def test_detach_removes_matching_interface() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    removed = apply_interface_detach(
        document,
        InterfaceDetachChange("52:54:00:aa:bb:cc"),
    )

    assert "52:54:00:aa:bb:cc" == removed
    assert [] == document.root.findall("./devices/interface")


def test_detach_rejects_unknown_mac() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    with pytest.raises(NetworkConfigError, match="missing or ambiguous"):
        apply_interface_detach(
            document,
            InterfaceDetachChange("52:54:00:aa:bb:ee"),
        )


def test_update_switches_network_and_mac() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    apply_interface_update(
        document,
        InterfaceUpdateChange(
            "52:54:00:aa:bb:cc",
            kind="bridge",
            source="br0",
            new_mac="52:54:00:aa:bb:dd",
        ),
    )

    interface = document.root.find("./devices/interface")
    assert interface is not None
    assert "bridge" == interface.get("type")
    assert "br0" == interface.find("source").get("bridge")  # type: ignore[union-attr]
    assert "52:54:00:aa:bb:dd" == interface.find("mac").get("address")  # type: ignore[union-attr]


def test_update_requires_change_and_rejects_same_mac() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    with pytest.raises(NetworkConfigError, match="no changes"):
        apply_interface_update(
            document,
            InterfaceUpdateChange("52:54:00:aa:bb:cc"),
        )
    with pytest.raises(NetworkConfigError, match="must differ"):
        apply_interface_update(
            document,
            InterfaceUpdateChange("52:54:00:aa:bb:cc", new_mac="52:54:00:aa:bb:cc"),
        )


def test_verify_attach_accepts_libvirt_address_and_rejects_unrelated_changes() -> None:
    original = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    original_hash = original.fingerprint().digest

    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    change = InterfaceAttachChange("bridge", "br0", "virtio")
    apply_interface_attach(document, change)

    verify_interface_attach_result(document, change, original_hash=original_hash)

    document2 = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    apply_interface_attach(document2, change)
    other = document2.root.find("./devices/mystery")
    assert other is not None
    other.set("changed", "yes")
    with pytest.raises(NetworkConfigError, match="unrelated domain XML"):
        verify_interface_attach_result(
            document2,
            change,
            original_hash=original_hash,
        )


def test_attach_rejects_invalid_mac_and_model() -> None:
    with pytest.raises(NetworkConfigError, match="MAC"):
        InterfaceAttachChange("bridge", "br0", "virtio", "not-a-mac").validate()
    with pytest.raises(NetworkConfigError, match="model"):
        InterfaceAttachChange("bridge", "br0", "unknown").validate()
