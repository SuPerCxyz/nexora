"""Read-only extraction of advanced libvirt domain XML configuration.

Surfaces NUMA topology, CPU pinning (cputune), watchdog and vsock
elements for display without modifying the underlying XML.
"""

from dataclasses import dataclass

from lxml import etree

from nexora.xml.document import LibvirtXmlDocument
from nexora.xml.errors import XmlStructureError


@dataclass(frozen=True)
class NumaCell:
    """单个 NUMA cell 的只读视图。"""

    cell_id: int
    cpus: str | None
    memory_kib: int
    mem_access: str | None
    distances: list[tuple[int, int]]


@dataclass(frozen=True)
class CpuPinning:
    """单个 vCPU 或 emulator pinning 的只读视图。"""

    vcpu_id: int | None
    cpuset: str
    emulator: bool


@dataclass(frozen=True)
class WatchdogInfo:
    """watchdog 设备的只读视图。"""

    model: str
    action: str


@dataclass(frozen=True)
class VsockInfo:
    """vsock 设备的只读视图。"""

    auto_cid: bool
    cid: int | None


@dataclass(frozen=True)
class AdvancedConfig:
    """Domain XML 中高级配置的聚合只读视图。

    所有字段在元素不存在时为 None 或空列表，调用方可据此决定是否渲染。
    """

    numa_cells: list[NumaCell]
    cpu_pinning: list[CpuPinning]
    watchdog: WatchdogInfo | None
    vsock: VsockInfo | None

    @property
    def has_any(self) -> bool:
        """是否存在至少一项高级配置。"""
        return bool(
            self.numa_cells
            or self.cpu_pinning
            or self.watchdog is not None
            or self.vsock is not None
        )


def read_advanced_config(document: LibvirtXmlDocument) -> AdvancedConfig:
    """从 Domain XML 提取 NUMA、cputune、watchdog 和 vsock 只读信息。"""

    root = document.root
    if etree.QName(root).localname != "domain":
        raise XmlStructureError("advanced config requires a domain document")
    return AdvancedConfig(
        numa_cells=_numa_cells(root),
        cpu_pinning=_cpu_pinning(root),
        watchdog=_watchdog(root),
        vsock=_vsock(root),
    )


def _numa_cells(root: etree._Element) -> list[NumaCell]:
    cpu = root.find("cpu")
    if cpu is None:
        return []
    numa = cpu.find("numa")
    if numa is None:
        return []
    cells: list[NumaCell] = []
    for cell in numa.findall("cell"):
        cell_id = int(cell.get("id", "0"))
        cpus = cell.get("cpus")
        memory_kib = _int_attr(cell, "memory", 0)
        mem_access = cell.get("memAccess")
        distances: list[tuple[int, int]] = []
        for sibling in cell.findall("distances/sibling"):
            sibling_id = _int_attr(sibling, "id", 0)
            value = _int_attr(sibling, "value", 0)
            distances.append((sibling_id, value))
        cells.append(
            NumaCell(
                cell_id=cell_id,
                cpus=cpus,
                memory_kib=memory_kib,
                mem_access=mem_access,
                distances=distances,
            )
        )
    return cells


def _cpu_pinning(root: etree._Element) -> list[CpuPinning]:
    cputune = root.find("cputune")
    if cputune is None:
        return []
    entries: list[CpuPinning] = []
    for pin in cputune.findall("vcpupin"):
        vcpu_id = int(pin.get("vcpu", "0"))
        cpuset = pin.get("cpuset", "")
        entries.append(CpuPinning(vcpu_id=vcpu_id, cpuset=cpuset, emulator=False))
    emulator = cputune.find("emulatorpin")
    if emulator is not None:
        entries.append(
            CpuPinning(
                vcpu_id=None,
                cpuset=emulator.get("cpuset", ""),
                emulator=True,
            )
        )
    return entries


def _watchdog(root: etree._Element) -> WatchdogInfo | None:
    device = root.find("devices/watchdog")
    if device is None:
        return None
    return WatchdogInfo(
        model=device.get("model", ""),
        action=device.get("action", ""),
    )


def _vsock(root: etree._Element) -> VsockInfo | None:
    device = root.find("devices/vsock")
    if device is None:
        return None
    cid_attr = device.find("cid")
    auto_cid = cid_attr is not None and cid_attr.get("auto", "no") == "yes"
    cid: int | None = None
    if cid_attr is not None:
        cid_text = cid_attr.get("address")
        if cid_text is not None:
            cid = int(cid_text)
    return VsockInfo(auto_cid=auto_cid, cid=cid)


def _int_attr(element: etree._Element, name: str, default: int) -> int:
    value = element.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
