"""Preservation-oriented libvirt network interface XML changes."""

import re
from dataclasses import dataclass

from lxml import etree

from nexora.xml.document import LibvirtXmlDocument

SUPPORTED_MODELS = frozenset({"virtio", "e1000e", "e1000", "rtl8139"})
MAC_PATTERN = re.compile(r"(?i)([0-9a-f]{2}:){5}[0-9a-f]{2}")


class NetworkConfigError(ValueError):
    pass


@dataclass(frozen=True)
class InterfaceAttachChange:
    kind: str
    source: str
    model: str
    mac: str | None = None

    def validate(self) -> None:
        if self.kind not in {"bridge", "network"}:
            raise NetworkConfigError("interface kind is unsupported")
        if not self.source or "\0" in self.source or len(self.source) > 128:
            raise NetworkConfigError("interface source is invalid")
        if self.model not in SUPPORTED_MODELS:
            raise NetworkConfigError("interface model is unsupported")
        if self.mac is not None and MAC_PATTERN.fullmatch(self.mac) is None:
            raise NetworkConfigError("interface MAC is invalid")


@dataclass(frozen=True)
class InterfaceDetachChange:
    mac: str

    def validate(self) -> None:
        if MAC_PATTERN.fullmatch(self.mac) is None:
            raise NetworkConfigError("interface MAC is invalid")


@dataclass(frozen=True)
class InterfaceUpdateChange:
    mac: str
    kind: str | None = None
    source: str | None = None
    model: str | None = None
    new_mac: str | None = None

    def validate(self) -> None:
        if MAC_PATTERN.fullmatch(self.mac) is None:
            raise NetworkConfigError("interface MAC is invalid")
        if self.new_mac is not None and MAC_PATTERN.fullmatch(self.new_mac) is None:
            raise NetworkConfigError("interface new MAC is invalid")
        if self.kind is not None and self.kind not in {"bridge", "network"}:
            raise NetworkConfigError("interface kind is unsupported")
        if self.source is not None and (
            not self.source or "\0" in self.source or len(self.source) > 128
        ):
            raise NetworkConfigError("interface source is invalid")
        if self.model is not None and self.model not in SUPPORTED_MODELS:
            raise NetworkConfigError("interface model is unsupported")
        if self.new_mac is not None and self.new_mac == self.mac:
            raise NetworkConfigError("interface new MAC must differ")
        if (
            self.kind is None
            and self.source is None
            and self.model is None
            and self.new_mac is None
        ):
            raise NetworkConfigError("interface update has no changes")


def apply_interface_attach(
    document: LibvirtXmlDocument,
    change: InterfaceAttachChange,
) -> str:
    change.validate()
    devices = document.root.find("devices")
    if devices is None:
        raise NetworkConfigError("domain XML is missing devices")
    if change.mac is not None and any(
        _mac(interface) == change.mac for interface in devices.findall("interface")
    ):
        raise NetworkConfigError("interface MAC is already attached")
    if any(_source_name(interface) == change.source for interface in devices.findall("interface")):
        raise NetworkConfigError("interface source is already attached")
    interface = etree.Element("interface", type=change.kind)
    if change.mac is not None:
        etree.SubElement(interface, "mac", address=change.mac)
    source_attribute = "bridge" if change.kind == "bridge" else "network"
    etree.SubElement(interface, "source", attrib={source_attribute: change.source})
    etree.SubElement(interface, "model", type=change.model)
    devices.append(interface)
    return change.source


def apply_interface_detach(
    document: LibvirtXmlDocument,
    change: InterfaceDetachChange,
) -> str:
    change.validate()
    devices = document.root.find("devices")
    if devices is None:
        raise NetworkConfigError("domain XML is missing devices")
    matches = [
        interface for interface in devices.findall("interface") if _mac(interface) == change.mac
    ]
    if len(matches) != 1:
        raise NetworkConfigError("interface MAC is missing or ambiguous")
    devices.remove(matches[0])
    return change.mac


def apply_interface_update(
    document: LibvirtXmlDocument,
    change: InterfaceUpdateChange,
) -> str:
    change.validate()
    devices = document.root.find("devices")
    if devices is None:
        raise NetworkConfigError("domain XML is missing devices")
    matches = [
        interface for interface in devices.findall("interface") if _mac(interface) == change.mac
    ]
    if len(matches) != 1:
        raise NetworkConfigError("interface MAC is missing or ambiguous")
    interface = matches[0]
    if change.kind is not None:
        interface.set("type", change.kind)
    if change.source is not None:
        source = interface.find("source")
        if source is None:
            source = etree.SubElement(interface, "source")
        for attribute in ("bridge", "network", "dev"):
            if attribute in source.attrib:
                del source.attrib[attribute]
        source.set("bridge" if change.kind == "bridge" else "network", change.source)
    if change.model is not None:
        model = interface.find("model")
        if model is None:
            model = etree.SubElement(interface, "model")
        model.set("type", change.model)
    if change.new_mac is not None:
        mac = interface.find("mac")
        if mac is None:
            mac = etree.Element("mac")
            interface.insert(0, mac)
        mac.set("address", change.new_mac)
    return change.mac


def verify_interface_attach_result(
    document: LibvirtXmlDocument,
    change: InterfaceAttachChange,
    *,
    original_hash: str,
) -> None:
    """Accept only the requested interface plus libvirt's generated address/target."""

    change.validate()
    devices = document.root.find("devices")
    if devices is None:
        raise NetworkConfigError("authoritative domain XML is missing devices")
    matches = [
        interface
        for interface in devices.findall("interface")
        if interface.get("type") == change.kind and _source_name(interface) == change.source
    ]
    if len(matches) != 1:
        raise NetworkConfigError("attached interface is missing or ambiguous")
    interface = matches[0]
    mac = interface.find("mac")
    model = interface.find("model")
    allowed_children = {
        "mac",
        "source",
        "model",
        "target",
        "address",
        "link",
        "boot",
        "rom",
        "driver",
        "alias",
    }
    if (
        len(interface.attrib) != 1
        or interface.get("type") != change.kind
        or (
            change.mac is not None
            and (mac is None or (mac.get("address") or "").lower() != change.mac.lower())
        )
        or (change.mac is None and mac is not None)
        or model is None
        or (model.get("type") or "") != change.model
        or any(child.tag not in allowed_children for child in interface)
    ):
        raise NetworkConfigError("authoritative attached interface differs from the plan")
    devices.remove(interface)
    if document.fingerprint().digest != original_hash:
        raise NetworkConfigError("libvirt changed unrelated domain XML")


def _mac(interface: etree._Element) -> str | None:
    mac = interface.find("mac")
    value = mac.get("address") if mac is not None else None
    return value.lower() if isinstance(value, str) else None


def _source_name(interface: etree._Element) -> str | None:
    source = interface.find("source")
    if source is None:
        return None
    for attribute in ("bridge", "network", "dev"):
        value = source.get(attribute)
        if value is not None:
            return value
    return None
