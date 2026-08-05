"""Safe extraction of bounded virtual machine discovery metadata."""

from uuid import UUID

from lxml import etree

from nexora.resources.contracts import ResourceObservation
from nexora.resources.models import ResourceStatus
from nexora.xml.advanced_config import read_advanced_config
from nexora.xml.document import HASH_ALGORITHM, LibvirtXmlDocument
from nexora.xml.errors import XmlSafetyError, XmlStructureError

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


def parse_domain_observation(
    domain_uuid: str,
    persistent_xml: bytes | None,
    live_xml: bytes | None,
    *,
    state: str,
    autostart: bool,
) -> ResourceObservation:
    canonical_uuid = str(UUID(domain_uuid))
    if persistent_xml is None and live_xml is None:
        raise XmlStructureError("domain has no readable XML")
    persistent = _parse_domain(persistent_xml, canonical_uuid)
    live = _parse_domain(live_xml, canonical_uuid)
    source = persistent or live
    if source is None:
        raise XmlStructureError("domain has no readable XML")
    name = _required_text(source, "name")
    details: dict[str, object] = {
        "name": name,
        "state": state,
        "persistent": persistent is not None,
        "autostart": autostart,
        "memory_kib": _memory_kib(source),
        "maximum_vcpus": _maximum_vcpus(source),
        "current_vcpus": _current_vcpus(source),
        "disks": _disks(source),
        "interfaces": _interfaces(source),
        "host_devices": _host_devices(source),
        "advanced_config": _advanced_config(source),
    }
    documents: dict[str, bytes] = {}
    if persistent_xml is not None:
        documents["persistent_xml"] = persistent_xml
    if live_xml is not None:
        documents["live_xml"] = live_xml
    return ResourceObservation(
        native_id=canonical_uuid,
        display_name=name,
        status=(ResourceStatus.MANAGED if persistent is not None else ResourceStatus.TRANSIENT),
        persistent_hash=persistent.fingerprint().digest if persistent else None,
        live_hash=live.fingerprint().digest if live else None,
        hash_algorithm=HASH_ALGORITHM,
        details=details,
        documents=documents,
    )


def _parse_domain(
    content: bytes | None,
    expected_uuid: str,
) -> LibvirtXmlDocument | None:
    if content is None:
        return None
    document = LibvirtXmlDocument.parse(content, expected_root="domain")
    actual_uuid = _required_text(document, "uuid")
    try:
        canonical_actual = str(UUID(actual_uuid))
    except ValueError as exc:
        raise XmlStructureError("domain XML contains an invalid UUID") from exc
    if canonical_actual != expected_uuid:
        raise XmlStructureError("domain XML UUID does not match requested domain")
    return document


def _required_text(document: LibvirtXmlDocument, path: str) -> str:
    value = document.root.findtext(path)
    if value is None or not value.strip():
        raise XmlStructureError(f"domain XML is missing {path}")
    return value.strip()


def _memory_kib(document: LibvirtXmlDocument) -> int:
    element = document.root.find("memory")
    if element is None or element.text is None:
        return 0
    try:
        value = int(element.text.strip())
    except ValueError as exc:
        raise XmlStructureError("domain memory is invalid") from exc
    unit = element.get("unit", "KiB").lower()
    multiplier = MEMORY_TO_KIB.get(unit)
    if multiplier is None:
        raise XmlStructureError("domain memory unit is unsupported")
    return int(value * multiplier)


def _maximum_vcpus(document: LibvirtXmlDocument) -> int:
    element = document.root.find("vcpu")
    if element is None or element.text is None:
        return 0
    try:
        return int(element.text.strip())
    except ValueError as exc:
        raise XmlStructureError("domain vCPU count is invalid") from exc


def _current_vcpus(document: LibvirtXmlDocument) -> int:
    element = document.root.find("vcpu")
    if element is None:
        return 0
    current = element.get("current")
    if current is None:
        return _maximum_vcpus(document)
    try:
        return int(current)
    except ValueError as exc:
        raise XmlStructureError("domain current vCPU count is invalid") from exc


def _disks(document: LibvirtXmlDocument) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for disk in document.root.findall("./devices/disk"):
        driver = disk.find("driver")
        source = disk.find("source")
        target = disk.find("target")
        boot = disk.find("boot")
        values.append(
            {
                "type": disk.get("type"),
                "device": disk.get("device"),
                "source": _first_attribute(source, ("file", "dev", "name", "volume")),
                "pool": source.get("pool") if source is not None else None,
                "target": target.get("dev") if target is not None else None,
                "bus": target.get("bus") if target is not None else None,
                "format": driver.get("type") if driver is not None else None,
                "cache": driver.get("cache") if driver is not None else None,
                "io": driver.get("io") if driver is not None else None,
                "discard": driver.get("discard") if driver is not None else None,
                "serial": disk.findtext("serial"),
                "boot_order": boot.get("order") if boot is not None else None,
                "readonly": disk.find("readonly") is not None,
                "shareable": disk.find("shareable") is not None,
            }
        )
    return values


def _interfaces(document: LibvirtXmlDocument) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for interface in document.root.findall("./devices/interface"):
        source = interface.find("source")
        mac = interface.find("mac")
        target = interface.find("target")
        model = interface.find("model")
        values.append(
            {
                "type": interface.get("type"),
                "source": _first_attribute(source, ("bridge", "network", "dev")),
                "mac": mac.get("address") if mac is not None else None,
                "target": target.get("dev") if target is not None else None,
                "model": model.get("type") if model is not None else None,
            }
        )
    return values


def _host_devices(document: LibvirtXmlDocument) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for device in document.root.findall("./devices/hostdev"):
        address = device.find("./source/address")
        values.append(
            {
                "type": device.get("type"),
                "mode": device.get("mode"),
                "address": (
                    {str(key): str(value) for key, value in address.attrib.items()}
                    if address is not None
                    else None
                ),
            }
        )
    return values


def _first_attribute(
    element: etree._Element | None,
    names: tuple[str, ...],
) -> str | None:
    if element is None:
        return None
    for name in names:
        value = element.get(name)
        if value is not None:
            return value
    return None


def _advanced_config(document: LibvirtXmlDocument) -> dict[str, object] | None:
    try:
        config = read_advanced_config(document)
    except (XmlSafetyError, XmlStructureError):
        return None
    if not config.has_any:
        return None
    return {
        "numa_cells": [
            {
                "cell_id": cell.cell_id,
                "cpus": cell.cpus,
                "memory_kib": cell.memory_kib,
                "mem_access": cell.mem_access,
                "distances": cell.distances,
            }
            for cell in config.numa_cells
        ],
        "cpu_pinning": [
            {
                "vcpu_id": pin.vcpu_id,
                "cpuset": pin.cpuset,
                "emulator": pin.emulator,
            }
            for pin in config.cpu_pinning
        ],
        "watchdog": (
            {"model": config.watchdog.model, "action": config.watchdog.action}
            if config.watchdog is not None
            else None
        ),
        "vsock": (
            {"auto_cid": config.vsock.auto_cid, "cid": config.vsock.cid}
            if config.vsock is not None
            else None
        ),
    }
