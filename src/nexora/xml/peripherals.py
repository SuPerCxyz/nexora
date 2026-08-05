"""Targeted host-device and shared-directory domain XML changes."""

import re
from dataclasses import dataclass

from lxml import etree

from nexora.xml.document import LibvirtXmlDocument

TAG_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,36}$")
NEXORA_METADATA_NAMESPACE = "urn:nexora:managed"
VIRTIOFS_BACKING_MARKER = f"{{{NEXORA_METADATA_NAMESPACE}}}virtiofs-memory-backing"


class PeripheralConfigError(ValueError):
    pass


@dataclass(frozen=True)
class HostDeviceChange:
    device_type: str
    identity: tuple[str, ...]

    def validate(self) -> None:
        if self.device_type == "pci":
            if len(self.identity) != 4 or any(
                not value.startswith("0x") for value in self.identity
            ):
                raise PeripheralConfigError("PCI device identity is invalid")
        elif self.device_type == "usb":
            if len(self.identity) != 2 or any(not value.isdigit() for value in self.identity):
                raise PeripheralConfigError("USB device identity is invalid")
        else:
            raise PeripheralConfigError("host device type is unsupported")


@dataclass(frozen=True)
class SharedDirectoryChange:
    source_path: str
    target_tag: str
    driver: str
    readonly: bool = False

    def validate(self) -> None:
        if not self.source_path.startswith("/") or "\0" in self.source_path:
            raise PeripheralConfigError("shared directory path is invalid")
        if TAG_PATTERN.fullmatch(self.target_tag) is None:
            raise PeripheralConfigError("shared directory target tag is invalid")
        if self.driver not in {"virtiofs", "9p"}:
            raise PeripheralConfigError("shared directory driver is unsupported")


def apply_host_device_attach(document: LibvirtXmlDocument, change: HostDeviceChange) -> None:
    change.validate()
    devices = _devices(document)
    if any(_hostdev_identity(item) == change.identity for item in devices.findall("hostdev")):
        raise PeripheralConfigError("host device is already attached")
    hostdev = etree.Element("hostdev", mode="subsystem", type=change.device_type, managed="no")
    source = etree.SubElement(hostdev, "source")
    if change.device_type == "pci":
        etree.SubElement(
            source,
            "address",
            domain=change.identity[0],
            bus=change.identity[1],
            slot=change.identity[2],
            function=change.identity[3],
        )
    else:
        etree.SubElement(source, "address", bus=change.identity[0], device=change.identity[1])
    devices.append(hostdev)


def apply_host_device_detach(document: LibvirtXmlDocument, change: HostDeviceChange) -> None:
    change.validate()
    devices = _devices(document)
    matches = [
        item for item in devices.findall("hostdev") if _hostdev_identity(item) == change.identity
    ]
    if len(matches) != 1:
        raise PeripheralConfigError("host device attachment is missing or ambiguous")
    devices.remove(matches[0])


def apply_shared_directory_attach(
    document: LibvirtXmlDocument,
    change: SharedDirectoryChange,
) -> None:
    change.validate()
    devices = _devices(document)
    if any(_filesystem_target(item) == change.target_tag for item in devices.findall("filesystem")):
        raise PeripheralConfigError("shared directory target tag is already used")
    if change.driver == "virtiofs":
        _ensure_virtiofs_memory_backing(document)
    filesystem = etree.Element("filesystem", type="mount", accessmode="passthrough")
    driver_attributes = {"type": "virtiofs"} if change.driver == "virtiofs" else {"type": "path"}
    etree.SubElement(filesystem, "driver", attrib=driver_attributes)
    etree.SubElement(filesystem, "source", dir=change.source_path)
    etree.SubElement(filesystem, "target", dir=change.target_tag)
    if change.readonly:
        etree.SubElement(filesystem, "readonly")
    devices.append(filesystem)


def apply_shared_directory_detach(
    document: LibvirtXmlDocument,
    change: SharedDirectoryChange,
) -> None:
    change.validate()
    devices = _devices(document)
    matches = [
        item
        for item in devices.findall("filesystem")
        if _filesystem_target(item) == change.target_tag
        and _filesystem_source(item) == change.source_path
    ]
    if len(matches) != 1:
        raise PeripheralConfigError("shared directory attachment is missing or ambiguous")
    virtiofs = _filesystem_driver(matches[0]) == "virtiofs"
    devices.remove(matches[0])
    if virtiofs and not any(
        _filesystem_driver(item) == "virtiofs" for item in devices.findall("filesystem")
    ):
        _cleanup_virtiofs_memory_backing(document)


def verify_shared_directory_attach_result(
    document: LibvirtXmlDocument,
    change: SharedDirectoryChange,
    *,
    original_hash: str,
) -> None:
    """Accept the planned filesystem and libvirt's generated address only."""

    change.validate()
    devices = _devices(document)
    matches = [
        item
        for item in devices.findall("filesystem")
        if _filesystem_target(item) == change.target_tag
        and _filesystem_source(item) == change.source_path
    ]
    if len(matches) != 1:
        raise PeripheralConfigError("shared directory attachment is missing or ambiguous")
    filesystem = matches[0]
    driver = filesystem.find("driver")
    source = filesystem.find("source")
    target = filesystem.find("target")
    addresses = filesystem.findall("address")
    expected_driver = "virtiofs" if change.driver == "virtiofs" else "path"
    allowed_children = {"driver", "source", "target", "readonly", "address"}
    if (
        not _exact_attributes(filesystem, {"type": "mount", "accessmode": "passthrough"})
        or driver is None
        or not _exact_attributes(driver, {"type": expected_driver})
        or source is None
        or not _exact_attributes(source, {"dir": change.source_path})
        or target is None
        or not _exact_attributes(target, {"dir": change.target_tag})
        or change.readonly != (filesystem.find("readonly") is not None)
        or any(child.tag not in allowed_children for child in filesystem)
        or len(addresses) > 1
        or (addresses and addresses[0].get("type") != "pci")
    ):
        raise PeripheralConfigError("authoritative shared directory differs from the plan")
    apply_shared_directory_detach(document, change)
    if document.fingerprint().digest != original_hash:
        raise PeripheralConfigError("libvirt changed unrelated domain XML")


def _ensure_virtiofs_memory_backing(document: LibvirtXmlDocument) -> None:
    root = document.root
    backing = root.find("memoryBacking")
    if backing is None:
        backing = etree.Element("memoryBacking")
        _insert_before(root, backing, "vcpu")
    source = backing.find("source")
    access = backing.find("access")
    if source is not None and source.get("type") != "memfd":
        raise PeripheralConfigError("virtiofs requires memfd memory backing")
    if access is not None and access.get("mode") != "shared":
        raise PeripheralConfigError("virtiofs requires shared memory backing")
    source_added = source is None
    access_added = access is None
    if source_added:
        source = etree.SubElement(backing, "source", type="memfd")
    if access_added:
        access = etree.SubElement(backing, "access", mode="shared")
    if source_added or access_added:
        marker = _virtiofs_marker(root, create=True)
        assert marker is not None
        if source_added:
            marker.set("source-added", "true")
        if access_added:
            marker.set("access-added", "true")


def _cleanup_virtiofs_memory_backing(document: LibvirtXmlDocument) -> None:
    root = document.root
    marker = _virtiofs_marker(root, create=False)
    backing = root.find("memoryBacking")
    if marker is None or backing is None:
        return
    if marker.get("source-added") == "true":
        _remove_matching(backing, "source", "type", "memfd")
    if marker.get("access-added") == "true":
        _remove_matching(backing, "access", "mode", "shared")
    metadata = marker.getparent()
    assert metadata is not None
    metadata.remove(marker)
    if not len(metadata) and not metadata.attrib and not (metadata.text or "").strip():
        root.remove(metadata)
    if not len(backing) and not backing.attrib and not (backing.text or "").strip():
        root.remove(backing)


def _devices(document: LibvirtXmlDocument) -> etree._Element:
    devices = document.root.find("devices")
    if devices is None:
        raise PeripheralConfigError("domain XML is missing devices")
    return devices


def _hostdev_identity(element: etree._Element) -> tuple[str, ...] | None:
    address = element.find("./source/address")
    if address is None:
        return None
    if element.get("type") == "pci":
        return tuple(address.get(name, "") for name in ("domain", "bus", "slot", "function"))
    if element.get("type") == "usb":
        return tuple(address.get(name, "") for name in ("bus", "device"))
    return None


def _filesystem_source(element: etree._Element) -> str | None:
    source = element.find("source")
    return source.get("dir") if source is not None else None


def _filesystem_target(element: etree._Element) -> str | None:
    target = element.find("target")
    return target.get("dir") if target is not None else None


def _filesystem_driver(element: etree._Element) -> str | None:
    driver = element.find("driver")
    return driver.get("type") if driver is not None else None


def _exact_attributes(element: etree._Element, expected: dict[str, str]) -> bool:
    return len(element.attrib) == len(expected) and all(
        element.get(name) == value for name, value in expected.items()
    )


def _virtiofs_marker(
    root: etree._Element,
    *,
    create: bool,
) -> etree._Element | None:
    metadata = root.find("metadata")
    marker = metadata.find(VIRTIOFS_BACKING_MARKER) if metadata is not None else None
    if marker is not None or not create:
        return marker
    if metadata is None:
        metadata = etree.Element("metadata")
        _insert_before(root, metadata, "memory")
    return etree.SubElement(metadata, VIRTIOFS_BACKING_MARKER)


def _insert_before(parent: etree._Element, element: etree._Element, following: str) -> None:
    sibling = parent.find(following)
    if sibling is None:
        parent.append(element)
    else:
        sibling.addprevious(element)


def _remove_matching(
    parent: etree._Element,
    name: str,
    attribute: str,
    value: str,
) -> None:
    element = parent.find(name)
    if element is not None and element.get(attribute) == value:
        parent.remove(element)
