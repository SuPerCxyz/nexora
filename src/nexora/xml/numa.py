"""Targeted libvirt domain NUMA cell write operations."""

import re
from dataclasses import dataclass

from lxml import etree

from nexora.xml.document import LibvirtXmlDocument
from nexora.xml.errors import XmlStructureError

_CPUSET_PATTERN = re.compile(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")


class NumaConfigError(ValueError):
    """NUMA configuration is internally inconsistent."""


@dataclass(frozen=True)
class NumaCellChange:
    """A single NUMA cell to add or replace."""

    cell_id: int
    cpus: str
    memory_kib: int
    mem_access: str | None = None

    def validate(self) -> None:
        if self.cell_id < 0:
            raise NumaConfigError("NUMA cell id must be non-negative")
        if not _CPUSET_PATTERN.match(self.cpus):
            raise NumaConfigError("NUMA cell cpus format is invalid")
        if self.memory_kib < 1:
            raise NumaConfigError("NUMA cell memory must be positive")
        if self.mem_access is not None and self.mem_access not in {"shared", "private"}:
            raise NumaConfigError("NUMA memAccess is unsupported")


@dataclass(frozen=True)
class NumaChange:
    """A complete set of NUMA cells to apply."""

    cells: list[NumaCellChange]

    def validate(self, *, max_vcpus: int, memory_kib: int) -> None:
        if not self.cells:
            return
        seen_ids: set[int] = set()
        total_memory = 0
        all_cpus: set[int] = set()
        for cell in self.cells:
            cell.validate()
            if cell.cell_id in seen_ids:
                raise NumaConfigError("NUMA cell ids must be unique")
            seen_ids.add(cell.cell_id)
            total_memory += cell.memory_kib
            for cpu in _expand_cpus(cell.cpus):
                if cpu >= max_vcpus:
                    raise NumaConfigError(
                        f"NUMA cell {cell.cell_id} references vCPU {cpu} "
                        f"but maximum is {max_vcpus - 1}"
                    )
                if cpu in all_cpus:
                    raise NumaConfigError(f"NUMA cell {cell.cell_id} has overlapping vCPU {cpu}")
                all_cpus.add(cpu)
        if total_memory > memory_kib:
            raise NumaConfigError("NUMA cell memory total exceeds domain memory")


def read_numa_config(document: LibvirtXmlDocument) -> list[NumaCellChange]:
    """Read existing NUMA cells from the domain XML."""

    root = document.root
    if etree.QName(root).localname != "domain":
        raise XmlStructureError("NUMA config requires a domain document")
    cpu = root.find("cpu")
    if cpu is None:
        return []
    numa = cpu.find("numa")
    if numa is None:
        return []
    cells: list[NumaCellChange] = []
    for cell in numa.findall("cell"):
        cell_id = int(cell.get("id", "0"))
        cpus = cell.get("cpus", "")
        memory = int(cell.get("memory", "0"))
        mem_access = cell.get("memAccess")
        cells.append(NumaCellChange(cell_id, cpus, memory, mem_access))
    return cells


def apply_numa_change(
    document: LibvirtXmlDocument,
    change: NumaChange,
    *,
    max_vcpus: int,
    memory_kib: int,
) -> None:
    """Replace the complete NUMA section, preserving other cpu children."""

    change.validate(max_vcpus=max_vcpus, memory_kib=memory_kib)
    root = document.root
    if etree.QName(root).localname != "domain":
        raise XmlStructureError("NUMA config requires a domain document")
    cpu = root.find("cpu")
    if cpu is None:
        cpu = etree.Element("cpu")
        _insert_before(root, cpu, {"clock", "on_poweroff", "on_reboot", "on_crash", "devices"})
    existing_numa = cpu.find("numa")
    if existing_numa is not None:
        cpu.remove(existing_numa)
    if not change.cells:
        return
    numa = etree.SubElement(cpu, "numa")
    _insert_before(cpu, numa, {"cache", "maxphysaddr"})
    for cell in change.cells:
        attribs: dict[str, str] = {
            "id": str(cell.cell_id),
            "cpus": cell.cpus,
            "memory": str(cell.memory_kib),
            "unit": "KiB",
        }
        if cell.mem_access is not None:
            attribs["memAccess"] = cell.mem_access
        etree.SubElement(numa, "cell", attrib=attribs)


def _expand_cpus(cpus: str) -> list[int]:
    result: list[int] = []
    for part in cpus.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-")
            result.extend(range(int(start), int(end) + 1))
        else:
            result.append(int(part))
    return result


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
