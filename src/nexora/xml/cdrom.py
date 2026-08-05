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


def _target(disk: etree._Element) -> str | None:
    target = disk.find("target")
    return target.get("dev") if target is not None else None
