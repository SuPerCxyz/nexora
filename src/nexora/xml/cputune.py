"""Targeted libvirt domain CPU pinning (cputune) write operations."""

import re
from dataclasses import dataclass

from lxml import etree

from nexora.xml.document import LibvirtXmlDocument
from nexora.xml.errors import XmlStructureError

_CPUSET_PATTERN = re.compile(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")


class CpuTuneError(ValueError):
    """CPU pinning configuration is invalid."""


@dataclass(frozen=True)
class VcpuPinChange:
    """A single vCPU pinning entry."""

    vcpu_id: int
    cpuset: str

    def validate(self) -> None:
        if self.vcpu_id < 0:
            raise CpuTuneError("vCPU id must be non-negative")
        if not _CPUSET_PATTERN.match(self.cpuset):
            raise CpuTuneError("cpuset format is invalid")


@dataclass(frozen=True)
class EmulatorPinChange:
    """Emulator pinning entry."""

    cpuset: str

    def validate(self) -> None:
        if not _CPUSET_PATTERN.match(self.cpuset):
            raise CpuTuneError("emulator cpuset format is invalid")


@dataclass(frozen=True)
class CpuTuneChange:
    """A complete set of CPU pinning entries to apply."""

    vcpu_pins: list[VcpuPinChange]
    emulator_pin: EmulatorPinChange | None = None

    def validate(self, *, max_vcpus: int) -> None:
        seen: set[int] = set()
        for pin in self.vcpu_pins:
            pin.validate()
            if pin.vcpu_id >= max_vcpus:
                raise CpuTuneError(f"vCPU pin id {pin.vcpu_id} exceeds maximum {max_vcpus - 1}")
            if pin.vcpu_id in seen:
                raise CpuTuneError(f"duplicate vCPU pin for id {pin.vcpu_id}")
            seen.add(pin.vcpu_id)
        if self.emulator_pin is not None:
            self.emulator_pin.validate()


def read_cputune(document: LibvirtXmlDocument) -> CpuTuneChange:
    """Read existing cputune from the domain XML."""

    root = document.root
    if etree.QName(root).localname != "domain":
        raise XmlStructureError("cputune requires a domain document")
    cputune = root.find("cputune")
    if cputune is None:
        return CpuTuneChange([], None)
    vcpu_pins: list[VcpuPinChange] = []
    for pin in cputune.findall("vcpupin"):
        vcpu_pins.append(VcpuPinChange(int(pin.get("vcpu", "0")), pin.get("cpuset", "")))
    emulator = cputune.find("emulatorpin")
    emulator_pin = None
    if emulator is not None:
        emulator_pin = EmulatorPinChange(emulator.get("cpuset", ""))
    return CpuTuneChange(vcpu_pins, emulator_pin)


def apply_cputune_change(
    document: LibvirtXmlDocument,
    change: CpuTuneChange,
    *,
    max_vcpus: int,
) -> None:
    """Replace the complete cputune section, preserving other domain children."""

    change.validate(max_vcpus=max_vcpus)
    root = document.root
    if etree.QName(root).localname != "domain":
        raise XmlStructureError("cputune requires a domain document")
    existing = root.find("cputune")
    if existing is not None:
        root.remove(existing)
    if not change.vcpu_pins and change.emulator_pin is None:
        return
    cputune = etree.Element("cputune")
    _insert_before(root, cputune, {"numatune", "memory", "currentMemory", "vcpu"})
    for pin in change.vcpu_pins:
        etree.SubElement(cputune, "vcpupin", vcpu=str(pin.vcpu_id), cpuset=pin.cpuset)
    if change.emulator_pin is not None:
        etree.SubElement(cputune, "emulatorpin", cpuset=change.emulator_pin.cpuset)


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
