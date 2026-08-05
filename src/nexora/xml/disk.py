"""Preservation-oriented libvirt disk device XML changes."""

from dataclasses import dataclass

from lxml import etree

from nexora.xml.document import LibvirtXmlDocument

SUPPORTED_FORMATS = frozenset({"qcow2", "raw"})
SUPPORTED_BUSES = frozenset({"virtio", "sata", "scsi"})
SUPPORTED_CACHE = frozenset({"none", "writeback", "writethrough", "unsafe", "directsync"})
SUPPORTED_IO = frozenset({"native", "threads", "io_uring"})
SUPPORTED_DISCARD = frozenset({"ignore", "unmap"})


class DiskConfigError(ValueError):
    pass


@dataclass(frozen=True)
class DiskAttachChange:
    source_path: str
    volume_format: str
    bus: str
    cache: str | None = None
    io: str | None = None
    discard: str | None = None
    serial: str | None = None
    readonly: bool = False
    shareable: bool = False

    def validate(self) -> None:
        if not self.source_path.startswith("/") or "\0" in self.source_path:
            raise DiskConfigError("disk source path is invalid")
        if self.volume_format not in SUPPORTED_FORMATS:
            raise DiskConfigError("disk volume format is unsupported")
        if self.bus not in SUPPORTED_BUSES:
            raise DiskConfigError("disk bus is unsupported")
        if self.cache is not None and self.cache not in SUPPORTED_CACHE:
            raise DiskConfigError("disk cache mode is unsupported")
        if self.io is not None and self.io not in SUPPORTED_IO:
            raise DiskConfigError("disk io mode is unsupported")
        if self.discard is not None and self.discard not in SUPPORTED_DISCARD:
            raise DiskConfigError("disk discard mode is unsupported")
        if self.serial is not None and len(self.serial) > 40:
            raise DiskConfigError("disk serial is too long")
        if self.readonly and self.shareable:
            raise DiskConfigError("disk cannot be both readonly and shareable")


@dataclass(frozen=True)
class DiskDetachChange:
    target: str
    bus: str
    device: str
    source: str

    def validate(self) -> None:
        if not self.target or not self.source:
            raise DiskConfigError("disk identity is invalid")
        if self.bus not in SUPPORTED_BUSES or self.device != "disk":
            raise DiskConfigError("disk device is unsupported")


def apply_disk_attach(
    document: LibvirtXmlDocument,
    change: DiskAttachChange,
) -> str:
    change.validate()
    devices = document.root.find("devices")
    if devices is None:
        raise DiskConfigError("domain XML is missing devices")
    if any(_source(disk) == change.source_path for disk in devices.findall("disk")):
        raise DiskConfigError("disk source is already attached")
    if change.bus == "scsi" and not _has_virtio_scsi(devices):
        raise DiskConfigError("virtio-scsi controller is required")
    target = _next_target(devices, change.bus)
    disk = etree.Element("disk", type="file", device="disk")
    driver_attribs: dict[str, str] = {"name": "qemu", "type": change.volume_format}
    if change.cache is not None:
        driver_attribs["cache"] = change.cache
    if change.io is not None:
        driver_attribs["io"] = change.io
    if change.discard is not None:
        driver_attribs["discard"] = change.discard
    etree.SubElement(disk, "driver", attrib=driver_attribs)
    etree.SubElement(disk, "source", file=change.source_path)
    etree.SubElement(disk, "target", dev=target, bus=change.bus)
    if change.serial is not None:
        etree.SubElement(disk, "serial").text = change.serial
    if change.readonly:
        etree.SubElement(disk, "readonly")
    if change.shareable:
        etree.SubElement(disk, "shareable")
    devices.append(disk)
    return target


def apply_disk_detach(
    document: LibvirtXmlDocument,
    change: DiskDetachChange,
) -> str:
    change.validate()
    devices = document.root.find("devices")
    if devices is None:
        raise DiskConfigError("domain XML is missing devices")
    matches = [disk for disk in devices.findall("disk") if _target(disk) == change.target]
    if len(matches) != 1:
        raise DiskConfigError("disk target is missing or ambiguous")
    disk = matches[0]
    if (
        disk.get("device") != change.device
        or _bus(disk) != change.bus
        or _source(disk) != change.source
    ):
        raise DiskConfigError("disk identity changed after page load")
    devices.remove(disk)
    return change.source


def verify_disk_attach_result(
    document: LibvirtXmlDocument,
    change: DiskAttachChange,
    *,
    target: str,
    original_hash: str,
) -> None:
    """Accept only the requested disk plus libvirt's generated PCI address."""

    change.validate()
    devices = document.root.find("devices")
    if devices is None:
        raise DiskConfigError("authoritative domain XML is missing devices")
    matches = [disk for disk in devices.findall("disk") if _target(disk) == target]
    if len(matches) != 1:
        raise DiskConfigError("attached disk target is missing or ambiguous")
    disk = matches[0]
    driver = disk.find("driver")
    source = disk.find("source")
    target_node = disk.find("target")
    allowed_children = {"driver", "source", "target", "address", "serial", "readonly", "shareable"}
    expected_driver: dict[str, str] = {"name": "qemu", "type": change.volume_format}
    if change.cache is not None:
        expected_driver["cache"] = change.cache
    if change.io is not None:
        expected_driver["io"] = change.io
    if change.discard is not None:
        expected_driver["discard"] = change.discard
    serial_element = disk.find("serial")
    serial_ok = change.serial is None or (
        serial_element is not None and (serial_element.text or "") == change.serial
    )
    readonly_ok = change.readonly == (disk.find("readonly") is not None)
    shareable_ok = change.shareable == (disk.find("shareable") is not None)
    if (
        not _exact_attributes(disk, {"type": "file", "device": "disk"})
        or driver is None
        or not _exact_attributes(driver, expected_driver)
        or source is None
        or not _exact_attributes(source, {"file": change.source_path})
        or target_node is None
        or not _exact_attributes(target_node, {"dev": target, "bus": change.bus})
        or any(child.tag not in allowed_children for child in disk)
        or len(disk.findall("address")) > 1
        or not serial_ok
        or not readonly_ok
        or not shareable_ok
    ):
        raise DiskConfigError("authoritative attached disk differs from the plan")
    devices.remove(disk)
    if document.fingerprint().digest != original_hash:
        raise DiskConfigError("libvirt changed unrelated domain XML")


def _next_target(devices: etree._Element, bus: str) -> str:
    prefix = "vd" if bus == "virtio" else "sd"
    used = {target for disk in devices.findall("disk") if (target := _target(disk)) is not None}
    for index in range(256):
        candidate = prefix + _suffix(index)
        if candidate not in used:
            return candidate
    raise DiskConfigError("no free disk target is available")


def _exact_attributes(element: etree._Element, expected: dict[str, str]) -> bool:
    return len(element.attrib) == len(expected) and all(
        element.get(name) == value for name, value in expected.items()
    )


def _suffix(index: int) -> str:
    value = index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("a") + remainder) + result
    return result


def _source(disk: etree._Element) -> str | None:
    source = disk.find("source")
    if source is None:
        return None
    for attribute in ("file", "dev", "name", "volume"):
        value = source.get(attribute)
        if value is not None:
            return value
    return None


def _target(disk: etree._Element) -> str | None:
    target = disk.find("target")
    return target.get("dev") if target is not None else None


def _bus(disk: etree._Element) -> str | None:
    target = disk.find("target")
    return target.get("bus") if target is not None else None


def _has_virtio_scsi(devices: etree._Element) -> bool:
    return any(
        controller.get("type") == "scsi" and controller.get("model", "").startswith("virtio-scsi")
        for controller in devices.findall("controller")
    )
