import pytest

from nexora.xml.cdrom import (
    CdromConfigError,
    CdromHttpChange,
    CdromMediaChange,
    apply_cdrom_add,
    apply_cdrom_http,
    apply_cdrom_media,
)
from nexora.xml.document import LibvirtXmlDocument

DOMAIN = b"""\
<domain><devices>
  <disk type="file" device="cdrom">
    <driver name="qemu" type="raw"/>
    <target dev="sda" bus="sata" tray="open"/>
    <readonly/>
    <address type="drive" controller="0" bus="1" target="0" unit="0"/>
  </disk>
  <mystery preserve="yes"/>
</devices></domain>"""


def test_mount_and_eject_preserve_cdrom_identity_and_unknown_xml() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    apply_cdrom_media(
        document,
        CdromMediaChange("sda", "sata", None, "/isos/linux.iso"),
    )
    cdrom = document.root.find("./devices/disk")
    assert cdrom is not None
    assert "/isos/linux.iso" == cdrom.find("source").get("file")  # type: ignore[union-attr]
    assert cdrom.find("target").get("tray") is None  # type: ignore[union-attr]
    assert document.root.find("./devices/mystery") is not None

    apply_cdrom_media(
        document,
        CdromMediaChange("sda", "sata", "/isos/linux.iso", None),
    )
    assert cdrom.find("source") is None
    assert "open" == cdrom.find("target").get("tray")  # type: ignore[union-attr]
    assert cdrom.find("address") is not None


def test_cdrom_change_rejects_stale_source_identity() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    with pytest.raises(CdromConfigError, match="changed"):
        apply_cdrom_media(
            document,
            CdromMediaChange("sda", "sata", "/isos/old.iso", None),
        )


def test_http_iso_uses_network_source_without_embedding_a_secret() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    credential_id = "11111111-1111-4111-8111-111111111111"
    path = f"/media/content/{credential_id}"
    apply_cdrom_http(
        document,
        CdromHttpChange(
            "sda",
            "sata",
            None,
            "https",
            "nexora.example.test",
            8443,
            path,
            credential_id,
        ),
    )

    cdrom = document.root.find("./devices/disk")
    assert cdrom is not None and "network" == cdrom.get("type")
    source = cdrom.find("source")
    assert source is not None and path == source.get("name")
    assert "nexora.example.test" == source.find("host").get("name")  # type: ignore[union-attr]
    assert source.find("cookies") is None

    apply_cdrom_media(
        document,
        CdromMediaChange("sda", "sata", path, None),
    )
    assert "file" == cdrom.get("type")
    assert cdrom.find("source") is None


def test_add_cdrom_creates_empty_sata_device_with_controller() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    apply_cdrom_add(document, "sata")
    cdroms = document.root.findall("./devices/disk")
    added = [d for d in cdroms if d.get("device") == "cdrom"]
    assert len(added) == 2
    target = added[1].find("target")
    assert target is not None and target.get("bus") == "sata"
    assert target.get("dev") not in {"sda"}
    assert added[1].find("readonly") is not None
    assert any(
        controller.get("type") == "sata"
        for controller in document.root.findall("./devices/controller")
    )


def test_add_cdrom_rejects_unsupported_bus() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    with pytest.raises(CdromConfigError, match="bus"):
        apply_cdrom_add(document, "virtio")
