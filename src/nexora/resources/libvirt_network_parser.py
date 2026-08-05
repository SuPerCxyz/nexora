"""Safe parsing of libvirt virtual network XML and status."""

from dataclasses import dataclass
from uuid import UUID

from nexora.resources.contracts import ResourceObservation
from nexora.resources.models import ResourceStatus
from nexora.xml.document import HASH_ALGORITHM, LibvirtXmlDocument
from nexora.xml.errors import XmlStructureError


@dataclass(frozen=True)
class NetworkInfo:
    active: bool
    persistent: bool
    autostart: bool


def parse_network_info(content: bytes) -> NetworkInfo:
    fields: dict[str, str] = {}
    for line in content.decode("utf-8", errors="strict").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip().lower()] = value.strip()
    if not {"active", "persistent", "autostart"} <= fields.keys():
        raise XmlStructureError("libvirt network information is incomplete")
    return NetworkInfo(
        active=_enabled(fields["active"]),
        persistent=_enabled(fields["persistent"]),
        autostart=_enabled(fields["autostart"]),
    )


def parse_network_observation(
    expected_uuid: str,
    content: bytes,
    info: NetworkInfo,
) -> ResourceObservation:
    document = LibvirtXmlDocument.parse(content, expected_root="network")
    actual_uuid = _uuid(_required_text(document, "uuid"))
    if actual_uuid != expected_uuid:
        raise XmlStructureError("network XML UUID does not match requested network")
    name = _required_text(document, "name")
    forward = document.root.find("forward")
    mode = forward.get("mode", "isolated") if forward is not None else "isolated"
    bridge = document.root.find("bridge")
    ips = []
    for element in document.root.findall("ip"):
        dhcp = element.find("dhcp")
        ranges = (
            [{"start": item.get("start"), "end": item.get("end")} for item in dhcp.findall("range")]
            if dhcp is not None
            else []
        )
        ips.append(
            {
                "family": element.get("family", "ipv4"),
                "address": element.get("address"),
                "netmask": element.get("netmask"),
                "prefix": element.get("prefix"),
                "dhcp_ranges": ranges,
            }
        )
    return ResourceObservation(
        native_id=actual_uuid,
        display_name=name,
        status=(
            ResourceStatus.MANAGED
            if mode in {"nat", "isolated"}
            else ResourceStatus.PARTIALLY_SUPPORTED
        ),
        persistent_hash=document.fingerprint().digest,
        live_hash=None,
        hash_algorithm=HASH_ALGORITHM,
        details={
            "name": name,
            "forward_mode": mode,
            "active": info.active,
            "persistent": info.persistent,
            "autostart": info.autostart,
            "bridge": bridge.get("name") if bridge is not None else None,
            "ips": ips,
        },
        documents={"network_xml": content},
    )


def _required_text(document: LibvirtXmlDocument, path: str) -> str:
    value = document.root.findtext(path)
    if value is None or not value.strip():
        raise XmlStructureError(f"network XML is missing {path}")
    return value.strip()


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise XmlStructureError("network XML contains an invalid UUID") from exc


def _enabled(value: str) -> bool:
    return value.lower() in {"yes", "enable", "enabled", "active", "on", "1"}
