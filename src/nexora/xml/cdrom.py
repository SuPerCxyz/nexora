"""Preservation-oriented local ISO changes for existing CD-ROM devices."""

from dataclasses import dataclass
from uuid import UUID

from lxml import etree

from nexora.xml.document import LibvirtXmlDocument

SUPPORTED_CDROM_BUSES = frozenset({"ide", "sata", "scsi"})


class CdromConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CdromMediaChange:
    target: str
    bus: str
    expected_source: str | None
    new_source: str | None

    def validate(self) -> None:
        if not self.target or self.bus not in SUPPORTED_CDROM_BUSES:
            raise CdromConfigError("CD-ROM identity is invalid")
        for value in (self.expected_source, self.new_source):
            if value is not None and (not value.startswith("/") or "\0" in value):
                raise CdromConfigError("CD-ROM source path is invalid")
        if self.expected_source == self.new_source:
            raise CdromConfigError("CD-ROM media change has no effect")


@dataclass(frozen=True)
class CdromHttpChange:
    target: str
    bus: str
    expected_source: str | None
    protocol: str
    host: str
    port: int
    path: str
    credential_id: str

    def validate(self) -> None:
        CdromMediaChange(
            self.target,
            self.bus,
            self.expected_source,
            self.path,
        ).validate()
        try:
            UUID(self.credential_id)
        except ValueError as exc:
            raise CdromConfigError("media credential identity is invalid") from exc
        if (
            self.protocol not in {"http", "https"}
            or not self.host
            or not 1 <= self.port <= 65535
            or self.path != f"/media/content/{self.credential_id}"
        ):
            raise CdromConfigError("HTTP ISO source is invalid")


def apply_cdrom_media(
    document: LibvirtXmlDocument,
    change: CdromMediaChange,
) -> None:
    change.validate()
    devices = document.root.find("devices")
    if devices is None:
        raise CdromConfigError("domain XML is missing devices")
    matches = [
        disk
        for disk in devices.findall("disk")
        if disk.get("device") == "cdrom" and _target(disk) == change.target
    ]
    if len(matches) != 1:
        raise CdromConfigError("CD-ROM target is missing or ambiguous")
    cdrom = matches[0]
    target = cdrom.find("target")
    source = cdrom.find("source")
    current = _source_identity(source)
    if (
        cdrom.get("type") not in {"file", "network"}
        or target is None
        or target.get("bus") != change.bus
        or current != change.expected_source
    ):
        raise CdromConfigError("CD-ROM identity or source changed")
    if source is not None:
        cdrom.remove(source)
    if change.new_source is None:
        cdrom.set("type", "file")
        target.set("tray", "open")
        return
    source = etree.Element("source", file=change.new_source)
    cdrom.insert(cdrom.index(target), source)
    cdrom.set("type", "file")
    if "tray" in target.attrib:
        del target.attrib["tray"]
    if cdrom.find("readonly") is None:
        cdrom.append(etree.Element("readonly"))


def apply_cdrom_http(
    document: LibvirtXmlDocument,
    change: CdromHttpChange,
) -> None:
    change.validate()
    apply_cdrom_media(
        document,
        CdromMediaChange(
            change.target,
            change.bus,
            change.expected_source,
            change.path,
        ),
    )
    cdrom = next(
        disk
        for disk in document.root.findall("./devices/disk")
        if disk.get("device") == "cdrom" and _target(disk) == change.target
    )
    source = cdrom.find("source")
    assert source is not None
    source.attrib.clear()
    source.attrib.update({"protocol": change.protocol, "name": change.path})
    etree.SubElement(source, "host", name=change.host, port=str(change.port))
    cdrom.set("type", "network")


def _source_identity(source: etree._Element | None) -> str | None:
    if source is None:
        return None
    return source.get("file") or source.get("name")


def apply_cdrom_add(
    document: LibvirtXmlDocument,
    bus: str,
) -> str:
    """Add an empty CD-ROM device on the requested bus; returns the target name."""
    if bus not in SUPPORTED_CDROM_BUSES:
        raise CdromConfigError("CD-ROM bus is unsupported")
    devices = document.root.find("devices")
    if devices is None:
        raise CdromConfigError("domain XML is missing devices")
    target = _next_cdrom_target(devices, bus)
    cdrom = etree.Element("disk", type="file", device="cdrom")
    etree.SubElement(cdrom, "target", dev=target, bus=bus)
    etree.SubElement(cdrom, "readonly")
    if bus == "sata" and not _has_sata_controller(devices):
        controller = etree.Element("controller", type="sata", index="0")
        devices.append(controller)
    devices.append(cdrom)
    return target


def _next_cdrom_target(devices: etree._Element, bus: str) -> str:
    if bus == "ide":
        prefix, offset = "hd", 0
    else:
        prefix, offset = "sd", 0
    used = {_target(disk) for disk in devices.findall("disk")}
    for index in range(16):
        candidate = f"{prefix}{chr(ord('a') + index + offset)}"
        if candidate not in used:
            return candidate
    raise CdromConfigError("no free CD-ROM target is available")


def _has_sata_controller(devices: etree._Element) -> bool:
    return any(
        controller.get("type") == "sata"
        for controller in devices.findall("controller")
    )


def _target(disk: etree._Element) -> str | None:
    target = disk.find("target")
    return target.get("dev") if target is not None else None
