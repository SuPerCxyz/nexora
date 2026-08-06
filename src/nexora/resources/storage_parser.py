"""Safe bounded parsing of libvirt storage pool and volume XML."""

import copy
import json
from dataclasses import dataclass
from uuid import UUID

from lxml import etree

from nexora.resources.contracts import ResourceObservation
from nexora.resources.models import ResourceStatus
from nexora.xml.document import HASH_ALGORITHM, LibvirtXmlDocument
from nexora.xml.errors import XmlStructureError

WRITABLE_POOL_TYPES = {"dir", "netfs"}
FS_NAMESPACE = "http://libvirt.org/schemas/storagepool/fs/1.0"


@dataclass(frozen=True)
class PoolInfo:
    state: str
    active: bool
    persistent: bool
    autostart: bool


def parse_volume_list(content: bytes) -> list[str]:
    lines = content.decode("utf-8", errors="replace").splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().startswith("Name") and "Path" in line
        ),
        None,
    )
    if header_index is None:
        raise XmlStructureError("storage volume list header is missing")
    path_offset = lines[header_index].find("Path")
    names = [line[:path_offset].strip() for line in lines[header_index + 2 :] if line.strip()]
    if any(not name for name in names):
        raise XmlStructureError("storage volume list contains an empty name")
    if len(names) != len(set(names)):
        raise XmlStructureError("storage volume list contains duplicate names")
    return names


def parse_pool_observation(
    expected_uuid: str | None,
    content: bytes,
    info: PoolInfo,
) -> ResourceObservation:
    document = LibvirtXmlDocument.parse(content, expected_root="pool")
    actual_uuid = _canonical_uuid(_required_text(document, "uuid"), "pool")
    if expected_uuid is not None and actual_uuid != expected_uuid:
        raise XmlStructureError("pool XML UUID does not match requested pool")
    name = _required_text(document, "name")
    pool_type = document.root.get("type", "unknown")
    source_host = document.root.find("./source/host")
    source_dir = document.root.find("./source/dir")
    protocol = document.root.find("./source/protocol")
    mount_options = document.root.findall(f"{{{FS_NAMESPACE}}}mount_opts/{{{FS_NAMESPACE}}}option")
    return ResourceObservation(
        native_id=actual_uuid,
        display_name=name,
        status=(
            ResourceStatus.MANAGED if pool_type in WRITABLE_POOL_TYPES else ResourceStatus.READ_ONLY
        ),
        persistent_hash=_pool_configuration_hash(document),
        live_hash=None,
        hash_algorithm=HASH_ALGORITHM,
        details={
            "name": name,
            "pool_type": pool_type,
            "state": info.state,
            "active": info.active,
            "persistent": info.persistent,
            "autostart": info.autostart,
            "capacity_bytes": _size(document, "capacity"),
            "allocation_bytes": _size(document, "allocation"),
            "available_bytes": _size(document, "available"),
            "target_path": document.root.findtext("./target/path"),
            "source_host": source_host.get("name") if source_host is not None else None,
            "source_path": source_dir.get("path") if source_dir is not None else None,
            "nfs_version": protocol.get("ver") if protocol is not None else None,
            "mount_options": [item.get("name") for item in mount_options],
        },
        documents={"pool_xml": content},
    )


def parse_volume_observation(
    pool_uuid: str,
    content: bytes,
) -> ResourceObservation:
    document = LibvirtXmlDocument.parse(content, expected_root="volume")
    name = _required_text(document, "name")
    key = _required_text(document, "key")
    target_format = document.root.find("./target/format")
    return ResourceObservation(
        native_id=json.dumps([pool_uuid, key], separators=(",", ":")),
        parent_native_id=pool_uuid,
        display_name=name,
        status=ResourceStatus.MANAGED,
        persistent_hash=volume_configuration_hash(content),
        live_hash=None,
        hash_algorithm=HASH_ALGORITHM,
        details={
            "pool_uuid": pool_uuid,
            "name": name,
            "key": key,
            "volume_type": document.root.get("type", "unknown"),
            "capacity_bytes": _size(document, "capacity"),
            "allocation_bytes": _size(document, "allocation"),
            "path": document.root.findtext("./target/path"),
            "format": (
                target_format.get("type", "unknown") if target_format is not None else "unknown"
            ),
            "backing_path": document.root.findtext("./backingStore/path"),
        },
        documents={"volume_xml": content},
    )


def volume_configuration_hash(content: bytes) -> str:
    """Hash writable configuration while excluding dynamic allocation."""

    document = LibvirtXmlDocument.parse(content, expected_root="volume")
    root = copy.deepcopy(document.root)
    for path in ("allocation", "physical", "./target/timestamps"):
        element = root.find(path)
        if element is not None:
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
    normalized = LibvirtXmlDocument.parse(
        etree.tostring(root, encoding="utf-8"),
        expected_root="volume",
    )
    return normalized.fingerprint().digest


def parse_pool_info(content: bytes) -> PoolInfo:
    fields: dict[str, str] = {}
    for line in content.decode("utf-8", errors="strict").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip().lower()] = value.strip()
    if not {"state", "persistent", "autostart"} <= fields.keys():
        raise XmlStructureError("pool information is incomplete")
    state = fields["state"]
    return PoolInfo(
        state=state,
        active=state.lower() in {"running", "degraded"},
        persistent=_enabled(fields["persistent"]),
        autostart=_enabled(fields["autostart"]),
    )


def _required_text(document: LibvirtXmlDocument, path: str) -> str:
    value = document.root.findtext(path)
    if value is None or not value.strip():
        raise XmlStructureError(f"storage XML is missing {path}")
    return value.strip()


def _pool_configuration_hash(document: LibvirtXmlDocument) -> str:
    root = copy.deepcopy(document.root)
    for name in ("capacity", "allocation", "available"):
        element = root.find(name)
        if element is not None:
            root.remove(element)
    normalized = LibvirtXmlDocument.parse(
        etree.tostring(root, encoding="utf-8"),
        expected_root="pool",
    )
    return normalized.fingerprint().digest


def _canonical_uuid(value: str, label: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise XmlStructureError(f"{label} XML contains an invalid UUID") from exc


def _enabled(value: str) -> bool:
    return value.lower() in {"yes", "enable", "enabled", "on", "1"}


def _size(document: LibvirtXmlDocument, path: str) -> int | None:
    element = document.root.find(path)
    if element is None or element.text is None:
        return None
    try:
        value = int(element.text.strip())
    except ValueError as exc:
        raise XmlStructureError(f"storage {path} is invalid") from exc
    unit = element.get("unit", "bytes").lower()
    factors = {"b": 1, "bytes": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3}
    factor = factors.get(unit)
    if factor is None:
        raise XmlStructureError(f"storage {path} unit is unsupported")
    return value * factor
