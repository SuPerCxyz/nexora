"""Targeted watchdog, vsock, and CPU cache XML changes."""

from dataclasses import dataclass

from lxml import etree

from nexora.xml.document import LibvirtXmlDocument
from nexora.xml.errors import XmlStructureError

WATCHDOG_MODELS = frozenset({"i6300esb", "ib700"})
WATCHDOG_ACTIONS = frozenset({"reset", "shutdown", "poweroff", "pause", "none"})
CACHE_MODES = frozenset({"emulate", "passthrough", "disable"})


class AdvancedDeviceError(ValueError):
    pass


@dataclass(frozen=True)
class AdvancedDeviceChange:
    watchdog_model: str | None = None
    watchdog_action: str | None = None
    vsock_mode: str = "remove"
    vsock_cid: int | None = None
    cache_mode: str | None = None
    maxphysaddr_mode: str | None = None
    maxphysaddr_bits: int | None = None

    def validate(self) -> None:
        if (self.watchdog_model is None) != (self.watchdog_action is None):
            raise AdvancedDeviceError("watchdog model and action must be set together")
        if self.watchdog_model is not None and self.watchdog_model not in WATCHDOG_MODELS:
            raise AdvancedDeviceError("watchdog model is unsupported")
        if self.watchdog_action is not None and self.watchdog_action not in WATCHDOG_ACTIONS:
            raise AdvancedDeviceError("watchdog action is unsupported")
        if self.vsock_mode not in {"remove", "auto", "explicit"}:
            raise AdvancedDeviceError("vsock mode is unsupported")
        if self.vsock_mode == "explicit" and not 3 <= (self.vsock_cid or 0) <= 2**32 - 1:
            raise AdvancedDeviceError("vsock CID must be between 3 and 4294967295")
        if self.vsock_mode != "explicit" and self.vsock_cid is not None:
            raise AdvancedDeviceError("vsock CID is only valid in explicit mode")
        if self.cache_mode is not None and self.cache_mode not in CACHE_MODES:
            raise AdvancedDeviceError("CPU cache mode is unsupported")
        if self.maxphysaddr_mode not in {None, "emulate", "passthrough"}:
            raise AdvancedDeviceError("maxphysaddr mode is unsupported")
        if self.maxphysaddr_bits is not None and not 32 <= self.maxphysaddr_bits <= 64:
            raise AdvancedDeviceError("maxphysaddr bits must be between 32 and 64")
        if self.maxphysaddr_bits is not None and self.maxphysaddr_mode != "emulate":
            raise AdvancedDeviceError("maxphysaddr bits require emulate mode")


def apply_advanced_device_change(
    document: LibvirtXmlDocument,
    change: AdvancedDeviceChange,
) -> None:
    change.validate()
    root = document.root
    if etree.QName(root).localname != "domain":
        raise XmlStructureError("advanced device change requires a domain document")
    _watchdog(root, change)
    _vsock(root, change)
    _cpu(root, change)


def _watchdog(root: etree._Element, change: AdvancedDeviceChange) -> None:
    devices = _devices(root)
    existing = devices.find("watchdog")
    if existing is not None:
        devices.remove(existing)
    if change.watchdog_model is not None and change.watchdog_action is not None:
        devices.append(
            etree.Element("watchdog", model=change.watchdog_model, action=change.watchdog_action)
        )


def _vsock(root: etree._Element, change: AdvancedDeviceChange) -> None:
    devices = _devices(root)
    existing = devices.find("vsock")
    if existing is not None:
        devices.remove(existing)
    if change.vsock_mode == "remove":
        return
    vsock = etree.Element("vsock", model="virtio")
    attributes = {"auto": "yes"}
    if change.vsock_mode == "explicit":
        attributes = {"auto": "no", "address": str(change.vsock_cid)}
    etree.SubElement(vsock, "cid", attrib=attributes)
    devices.append(vsock)


def _cpu(root: etree._Element, change: AdvancedDeviceChange) -> None:
    cpu = root.find("cpu")
    if cpu is None and (change.cache_mode is not None or change.maxphysaddr_mode is not None):
        cpu = etree.Element("cpu")
        _insert_before(root, cpu, {"clock", "devices"})
    if cpu is None:
        return
    for name in ("cache", "maxphysaddr"):
        existing = cpu.find(name)
        if existing is not None:
            cpu.remove(existing)
    if change.cache_mode is not None:
        etree.SubElement(cpu, "cache", mode=change.cache_mode)
    if change.maxphysaddr_mode is not None:
        attributes = {"mode": change.maxphysaddr_mode}
        if change.maxphysaddr_bits is not None:
            attributes["bits"] = str(change.maxphysaddr_bits)
        etree.SubElement(cpu, "maxphysaddr", attrib=attributes)


def _devices(root: etree._Element) -> etree._Element:
    devices = root.find("devices")
    if devices is None:
        devices = etree.Element("devices")
        root.append(devices)
    return devices


def _insert_before(
    parent: etree._Element,
    element: etree._Element,
    following_names: set[str],
) -> None:
    for index, child in enumerate(parent):
        if isinstance(child.tag, str) and etree.QName(child).localname in following_names:
            parent.insert(index, element)
            return
    parent.append(element)
