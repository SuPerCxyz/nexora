"""Targeted libvirt domain memory and memoryBacking changes."""

from dataclasses import dataclass

from lxml import etree

from nexora.xml.document import LibvirtXmlDocument
from nexora.xml.errors import XmlStructureError

MEMORY_TO_KIB = {
    "b": 1 / 1024,
    "bytes": 1 / 1024,
    "k": 1,
    "kb": 1,
    "kib": 1,
    "m": 1024,
    "mb": 1024,
    "mib": 1024,
    "g": 1024 * 1024,
    "gb": 1024 * 1024,
    "gib": 1024 * 1024,
}
SOURCE_TYPES = frozenset({"file", "anonymous", "memfd"})
ACCESS_MODES = frozenset({"shared", "private"})
ALLOCATION_MODES = frozenset({"immediate", "ondemand"})


@dataclass(frozen=True)
class MemoryConfigChange:
    current_kib: int
    maximum_kib: int
    hugepages: bool = False
    locked: bool = False
    source_type: str | None = None
    access_mode: str | None = None
    allocation_mode: str | None = None
    discard: bool = False

    def validate(self) -> None:
        if self.current_kib < 1 or self.maximum_kib < 1:
            raise XmlStructureError("memory values must be positive")
        if self.current_kib > self.maximum_kib:
            raise XmlStructureError("current memory exceeds maximum memory")
        if self.source_type is not None and self.source_type not in SOURCE_TYPES:
            raise XmlStructureError("unsupported memory source type")
        if self.access_mode is not None and self.access_mode not in ACCESS_MODES:
            raise XmlStructureError("unsupported memory access mode")
        if self.allocation_mode is not None and self.allocation_mode not in ALLOCATION_MODES:
            raise XmlStructureError("unsupported memory allocation mode")


def read_memory_config(document: LibvirtXmlDocument) -> MemoryConfigChange:
    root = _domain_root(document)
    maximum = _memory_kib(root.find("memory"), "maximum memory")
    current_element = root.find("currentMemory")
    current = maximum if current_element is None else _memory_kib(current_element, "current memory")
    backing = root.find("memoryBacking")
    return MemoryConfigChange(
        current,
        maximum,
        hugepages=backing is not None and backing.find("hugepages") is not None,
        locked=backing is not None and backing.find("locked") is not None,
        source_type=_attribute(backing, "source", "type"),
        access_mode=_attribute(backing, "access", "mode"),
        allocation_mode=_attribute(backing, "allocation", "mode"),
        discard=backing is not None and backing.find("discard") is not None,
    )


def apply_memory_config(
    document: LibvirtXmlDocument,
    change: MemoryConfigChange,
) -> None:
    change.validate()
    root = _domain_root(document)
    memory = _element(root, "memory", {"currentMemory", "vcpu", "resource", "sysinfo"})
    current = _element(root, "currentMemory", {"vcpu", "resource", "sysinfo"})
    for element, value in ((memory, change.maximum_kib), (current, change.current_kib)):
        element.text = str(value)
        element.set("unit", "KiB")
    backing = root.find("memoryBacking")
    needs_backing = any(
        (
            change.hugepages,
            change.locked,
            change.source_type,
            change.access_mode,
            change.allocation_mode,
            change.discard,
        )
    )
    if backing is None and needs_backing:
        backing = etree.Element("memoryBacking")
        _insert_before(root, backing, {"memtune", "numatune", "vcpu", "resource", "sysinfo"})
    if backing is None:
        return
    _toggle(backing, "hugepages", change.hugepages)
    _toggle(backing, "locked", change.locked)
    _set_attribute(backing, "source", "type", change.source_type)
    _set_attribute(backing, "access", "mode", change.access_mode)
    _set_attribute(backing, "allocation", "mode", change.allocation_mode)
    _toggle(backing, "discard", change.discard)
    if not len(backing) and not backing.attrib and not (backing.text or "").strip():
        root.remove(backing)


def _domain_root(document: LibvirtXmlDocument) -> etree._Element:
    root = document.root
    if etree.QName(root).localname != "domain":
        raise XmlStructureError("memory configuration requires a domain document")
    return root


def _memory_kib(element: etree._Element | None, label: str) -> int:
    if element is None or element.text is None:
        raise XmlStructureError(f"domain XML does not define {label}")
    try:
        value = int(element.text.strip())
    except ValueError as exc:
        raise XmlStructureError(f"{label} is invalid") from exc
    multiplier = MEMORY_TO_KIB.get(element.get("unit", "KiB").lower())
    if multiplier is None or value < 1:
        raise XmlStructureError(f"{label} unit or value is invalid")
    return int(value * multiplier)


def _attribute(
    parent: etree._Element | None,
    child_name: str,
    attribute: str,
) -> str | None:
    child = parent.find(child_name) if parent is not None else None
    return child.get(attribute) if child is not None else None


def _element(
    parent: etree._Element,
    name: str,
    following_names: set[str],
) -> etree._Element:
    element = parent.find(name)
    if element is None:
        element = etree.Element(name)
        _insert_before(parent, element, following_names)
    return element


def _toggle(parent: etree._Element, name: str, enabled: bool) -> None:
    element = parent.find(name)
    if enabled and element is None:
        parent.append(etree.Element(name))
    elif not enabled and element is not None:
        parent.remove(element)


def _set_attribute(
    parent: etree._Element,
    name: str,
    attribute: str,
    value: str | None,
) -> None:
    element = parent.find(name)
    if value is None:
        if element is not None:
            parent.remove(element)
        return
    if element is None:
        element = etree.Element(name)
        parent.append(element)
    element.set(attribute, value)


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
