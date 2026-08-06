"""Targeted libvirt domain CPU topology changes."""

from dataclasses import dataclass
from math import prod

from lxml import etree

from nexora.xml.document import LibvirtXmlDocument
from nexora.xml.errors import CpuTopologyError, XmlStructureError

MAX_VCPUS = 1024

@dataclass(frozen=True)
class CpuTopologyChange:
    current_vcpus: int
    maximum_vcpus: int
    sockets: int
    dies: int
    clusters: int
    cores: int
    threads: int

    def validate(self) -> None:
        values = (
            self.current_vcpus,
            self.maximum_vcpus,
            self.sockets,
            self.dies,
            self.clusters,
            self.cores,
            self.threads,
        )
        if any(value < 1 for value in values):
            raise CpuTopologyError("CPU values must be positive")
        if self.maximum_vcpus > MAX_VCPUS:
            raise CpuTopologyError("maximum vCPU exceeds the supported limit")
        if self.current_vcpus > self.maximum_vcpus:
            raise CpuTopologyError("current vCPU exceeds maximum vCPU")
        dimensions = (self.sockets, self.dies, self.clusters, self.cores, self.threads)
        if prod(dimensions) > self.maximum_vcpus:
            raise CpuTopologyError("CPU topology product must not exceed maximum vCPU")
        if self.threads not in {1, 2}:
            raise CpuTopologyError("threads per core must be 1 or 2")


def read_cpu_topology(document: LibvirtXmlDocument) -> CpuTopologyChange:
    """Read a complete topology, deriving a conservative layout when absent."""

    root = document.root
    if etree.QName(root).localname != "domain":
        raise XmlStructureError("CPU topology requires a domain document")
    vcpu = root.find("vcpu")
    if vcpu is None or vcpu.text is None:
        raise CpuTopologyError("domain XML does not define maximum vCPU")
    maximum = _positive_integer(vcpu.text, "maximum vCPU")
    current = _positive_integer(vcpu.get("current", vcpu.text), "current vCPU")
    topology = root.find("cpu/topology")
    if topology is None:
        return CpuTopologyChange(current, maximum, 1, 1, 1, maximum, 1)
    values = {
        name: _positive_integer(topology.get(name, "1"), name)
        for name in ("sockets", "dies", "clusters", "cores", "threads")
    }
    change = CpuTopologyChange(current, maximum, **values)
    change.validate()
    return change


def apply_cpu_topology(
    document: LibvirtXmlDocument,
    change: CpuTopologyChange,
) -> None:
    """Update only vCPU and topology fields, preserving all other XML."""

    change.validate()
    root = document.root
    if etree.QName(root).localname != "domain":
        raise XmlStructureError("CPU topology requires a domain document")
    vcpu = root.find("vcpu")
    if vcpu is None:
        vcpu = etree.Element("vcpu")
        _insert_before(
            root, vcpu, {"resource", "sysinfo", "os", "features", "cpu", "clock", "devices"}
        )
    vcpu.text = str(change.maximum_vcpus)
    vcpu.set("current", str(change.current_vcpus))

    cpu = root.find("cpu")
    if cpu is None:
        cpu = etree.Element("cpu")
        _insert_before(root, cpu, {"clock", "on_poweroff", "on_reboot", "on_crash", "devices"})
    topology = cpu.find("topology")
    if topology is None:
        topology = etree.Element("topology")
        _insert_before(cpu, topology, {"feature", "numa", "cache", "maxphysaddr"})
    topology_values = {
        "sockets": change.sockets,
        "dies": change.dies,
        "clusters": change.clusters,
        "cores": change.cores,
        "threads": change.threads,
    }
    for attribute, value in topology_values.items():
        topology.set(attribute, str(value))


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


def _positive_integer(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise CpuTopologyError(f"{label} is not an integer") from exc
    if parsed < 1:
        raise CpuTopologyError(f"{label} must be positive")
    return parsed
