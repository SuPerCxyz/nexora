import pytest
from lxml import etree

from nexora.xml.disk import (
    DiskAttachChange,
    DiskConfigError,
    DiskDetachChange,
    apply_disk_attach,
    apply_disk_detach,
    verify_disk_attach_result,
)
from nexora.xml.document import LibvirtXmlDocument

DOMAIN = b"""\
<domain type="kvm">
  <name>vm</name>
  <uuid>11111111-1111-1111-1111-111111111111</uuid>
  <devices>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2" cache="none"/>
      <source file="/images/root.qcow2"/>
      <target dev="vda" bus="virtio"/>
      <alias name="ua-root"/>
    </disk>
    <mystery keep="yes"/>
  </devices>
</domain>"""


def test_attach_allocates_target_and_preserves_unknown_devices() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    target = apply_disk_attach(
        document,
        DiskAttachChange("/images/data.qcow2", "qcow2", "virtio"),
    )

    assert "vdb" == target
    disk = document.root.xpath("./devices/disk[target/@dev='vdb']")[0]
    assert "/images/data.qcow2" == disk.find("source").get("file")  # type: ignore[union-attr]
    assert "yes" == document.root.find("./devices/mystery").get("keep")  # type: ignore[union-attr]
    assert "ua-root" == document.root.find("./devices/disk/alias").get("name")  # type: ignore[union-attr]


def test_attach_rejects_duplicate_source() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    with pytest.raises(DiskConfigError, match="already attached"):
        apply_disk_attach(
            document,
            DiskAttachChange("/images/root.qcow2", "qcow2", "virtio"),
        )


def test_detach_requires_full_device_identity_and_preserves_backing_reference() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    removed = apply_disk_detach(
        document,
        DiskDetachChange("vda", "virtio", "disk", "/images/root.qcow2"),
    )

    assert "/images/root.qcow2" == removed
    assert document.root.find("./devices/disk") is None
    assert document.root.find("./devices/mystery") is not None


def test_detach_rejects_tampered_source() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    with pytest.raises(DiskConfigError, match="identity changed"):
        apply_disk_detach(
            document,
            DiskDetachChange("vda", "virtio", "disk", "/images/other.qcow2"),
        )


def test_attach_verification_accepts_libvirt_generated_address() -> None:
    original = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    actual = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    change = DiskAttachChange("/images/data.qcow2", "qcow2", "virtio")
    target = apply_disk_attach(actual, change)
    disk = actual.root.xpath("./devices/disk[target/@dev='vdb']")[0]
    address = etree.SubElement(disk, "address")
    address.attrib.update(
        {
            "type": "pci",
            "domain": "0x0000",
            "bus": "0x00",
            "slot": "0x07",
            "function": "0x0",
        }
    )

    verify_disk_attach_result(
        actual,
        change,
        target=target,
        original_hash=original.fingerprint().digest,
    )


def test_attach_verification_rejects_unrelated_xml_change() -> None:
    original = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    actual = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    change = DiskAttachChange("/images/data.qcow2", "qcow2", "virtio")
    target = apply_disk_attach(actual, change)
    actual.root.find("name").text = "tampered"  # type: ignore[union-attr]

    with pytest.raises(DiskConfigError, match="unrelated"):
        verify_disk_attach_result(
            actual,
            change,
            target=target,
            original_hash=original.fingerprint().digest,
        )


def test_attach_with_advanced_params_sets_all_attributes() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    change = DiskAttachChange(
        "/images/data.qcow2",
        "qcow2",
        "virtio",
        cache="none",
        io="native",
        discard="unmap",
        serial="data-disk-001",
        readonly=True,
    )
    target = apply_disk_attach(document, change)
    disk = document.root.xpath(f"./devices/disk[target/@dev='{target}']")[0]
    driver = disk.find("driver")
    assert driver.get("cache") == "none"
    assert driver.get("io") == "native"
    assert driver.get("discard") == "unmap"
    assert disk.find("serial").text == "data-disk-001"
    assert disk.find("readonly") is not None
    assert disk.find("shareable") is None


def test_attach_with_shareable_sets_element() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    change = DiskAttachChange(
        "/images/shared.qcow2",
        "qcow2",
        "virtio",
        shareable=True,
    )
    target = apply_disk_attach(document, change)
    disk = document.root.xpath(f"./devices/disk[target/@dev='{target}']")[0]
    assert disk.find("shareable") is not None
    assert disk.find("readonly") is None


def test_attach_rejects_readonly_and_shareable() -> None:
    with pytest.raises(DiskConfigError, match="both readonly and shareable"):
        DiskAttachChange(
            "/images/data.qcow2",
            "qcow2",
            "virtio",
            readonly=True,
            shareable=True,
        ).validate()


def test_attach_rejects_invalid_cache_mode() -> None:
    with pytest.raises(DiskConfigError, match="cache"):
        DiskAttachChange(
            "/images/data.qcow2",
            "qcow2",
            "virtio",
            cache="invalid",
        ).validate()


def test_attach_rejects_invalid_io_mode() -> None:
    with pytest.raises(DiskConfigError, match="io"):
        DiskAttachChange(
            "/images/data.qcow2",
            "qcow2",
            "virtio",
            io="invalid",
        ).validate()


def test_attach_verification_accepts_advanced_params() -> None:
    original = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    actual = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    change = DiskAttachChange(
        "/images/data.qcow2",
        "qcow2",
        "virtio",
        cache="writeback",
        io="threads",
        discard="unmap",
        serial="vol-serial",
        readonly=True,
    )
    target = apply_disk_attach(actual, change)
    disk = actual.root.xpath("./devices/disk[target/@dev='vdb']")[0]
    address = etree.SubElement(disk, "address")
    address.attrib.update(
        {"type": "pci", "domain": "0x0", "bus": "0x0", "slot": "0x5", "function": "0x0"}
    )

    verify_disk_attach_result(
        actual,
        change,
        target=target,
        original_hash=original.fingerprint().digest,
    )


def test_attach_verification_rejects_missing_serial() -> None:
    original = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    actual = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    change = DiskAttachChange(
        "/images/data.qcow2",
        "qcow2",
        "virtio",
        serial="expected-serial",
    )
    target = apply_disk_attach(actual, change)
    disk = actual.root.xpath("./devices/disk[target/@dev='vdb']")[0]
    serial_el = disk.find("serial")
    disk.remove(serial_el)
    address = etree.SubElement(disk, "address")
    address.attrib.update(
        {"type": "pci", "domain": "0x0", "bus": "0x0", "slot": "0x5", "function": "0x0"}
    )

    with pytest.raises(DiskConfigError, match="differs"):
        verify_disk_attach_result(
            actual,
            change,
            target=target,
            original_hash=original.fingerprint().digest,
        )
