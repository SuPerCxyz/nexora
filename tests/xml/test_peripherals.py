import pytest
from lxml import etree

from nexora.xml import (
    HostDeviceChange,
    LibvirtXmlDocument,
    PeripheralConfigError,
    SharedDirectoryChange,
    apply_host_device_attach,
    apply_host_device_detach,
    apply_shared_directory_attach,
    apply_shared_directory_detach,
    verify_shared_directory_attach_result,
)

DOMAIN = b"""<domain type="kvm" xmlns:vendor="urn:vendor">
<name>guest</name><devices><vendor:keep/></devices></domain>"""


def test_host_device_attach_and_detach_preserve_unknown_devices() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    change = HostDeviceChange("pci", ("0x0000", "0x03", "0x00", "0x0"))
    apply_host_device_attach(document, change)
    hostdev = document.root.find("./devices/hostdev")
    assert hostdev.get("managed") == "no"
    assert hostdev.find("./source/address").get("bus") == "0x03"
    apply_host_device_detach(document, change)
    assert document.root.find("./devices/{urn:vendor}keep") is not None


def test_shared_directory_attach_and_detach() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    change = SharedDirectoryChange("/srv/share", "shared-data", "virtiofs", True)
    apply_shared_directory_attach(document, change)
    filesystem = document.root.find("./devices/filesystem")
    assert filesystem.find("driver").get("type") == "virtiofs"
    assert filesystem.find("readonly") is not None
    assert document.root.find("./memoryBacking/source").get("type") == "memfd"
    assert document.root.find("./memoryBacking/access").get("mode") == "shared"
    apply_shared_directory_detach(document, change)
    assert document.root.find("./devices/filesystem") is None
    assert document.root.find("./memoryBacking") is None


def test_virtiofs_preserves_existing_shared_memory_backing() -> None:
    document = LibvirtXmlDocument.parse(
        DOMAIN.replace(
            b"<devices>",
            b'<memoryBacking><source type="memfd"/><access mode="shared"/>'
            b"<locked/></memoryBacking><devices>",
        ),
        expected_root="domain",
    )
    change = SharedDirectoryChange("/srv/share", "shared-data", "virtiofs")
    apply_shared_directory_attach(document, change)
    apply_shared_directory_detach(document, change)
    assert document.root.find("./memoryBacking/source").get("type") == "memfd"
    assert document.root.find("./memoryBacking/access").get("mode") == "shared"
    assert document.root.find("./memoryBacking/locked") is not None


def test_virtiofs_rejects_conflicting_memory_backing() -> None:
    document = LibvirtXmlDocument.parse(
        DOMAIN.replace(
            b"<devices>",
            b'<memoryBacking><source type="file"/></memoryBacking><devices>',
        ),
        expected_root="domain",
    )
    change = SharedDirectoryChange("/srv/share", "shared-data", "virtiofs")
    with pytest.raises(PeripheralConfigError, match="memory backing"):
        apply_shared_directory_attach(document, change)


def test_virtiofs_attach_verification_accepts_generated_address_only() -> None:
    document = LibvirtXmlDocument.parse(
        b"""<domain type="kvm"><name>guest</name><uuid>11111111-1111-1111-1111-111111111111</uuid>
        <memory unit="KiB">1048576</memory><currentMemory unit="KiB">1048576</currentMemory>
        <vcpu>1</vcpu><devices/></domain>""",
        expected_root="domain",
    )
    change = SharedDirectoryChange("/srv/share", "shared-data", "virtiofs", True)
    original_hash = document.fingerprint().digest
    apply_shared_directory_attach(document, change)
    assert document.root.index(document.root.find("metadata")) < document.root.index(
        document.root.find("memory")
    )
    assert document.root.index(document.root.find("memoryBacking")) < document.root.index(
        document.root.find("vcpu")
    )
    filesystem = document.root.find("./devices/filesystem")
    etree.SubElement(filesystem, "address", type="pci", slot="0x06")
    verify_shared_directory_attach_result(document, change, original_hash=original_hash)
    assert document.fingerprint().digest == original_hash


def test_virtiofs_attach_verification_rejects_unrelated_change() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    change = SharedDirectoryChange("/srv/share", "shared-data", "9p")
    original_hash = document.fingerprint().digest
    apply_shared_directory_attach(document, change)
    document.root.set("id", "unexpected")
    with pytest.raises(PeripheralConfigError, match="unrelated"):
        verify_shared_directory_attach_result(document, change, original_hash=original_hash)


def test_peripherals_reject_duplicate_or_invalid_identity() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    change = SharedDirectoryChange("/srv/share", "bad tag", "9p")
    with pytest.raises(PeripheralConfigError):
        apply_shared_directory_attach(document, change)
