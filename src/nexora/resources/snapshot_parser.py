"""Safe libvirt domain snapshot XML parsing."""

import json
from datetime import UTC, datetime

from lxml import etree

from nexora.resources.contracts import ResourceObservation
from nexora.resources.models import ResourceStatus
from nexora.xml.document import HASH_ALGORITHM, LibvirtXmlDocument
from nexora.xml.errors import XmlStructureError


def parse_snapshot_observation(
    domain_uuid: str,
    snapshot_name: str,
    content: bytes,
    *,
    current: bool = False,
) -> ResourceObservation:
    document = LibvirtXmlDocument.parse(content, expected_root="domainsnapshot")
    actual_name = document.root.findtext("name")
    if actual_name is None or actual_name != snapshot_name:
        raise XmlStructureError("snapshot XML name does not match requested snapshot")
    creation_text = document.root.findtext("creationTime")
    creation_time = _timestamp(creation_text)
    memory = document.root.find("memory")
    domain = document.root.find("domain")
    domain_hash = (
        LibvirtXmlDocument.parse(
            etree.tostring(domain),
            expected_root="domain",
        )
        .fingerprint()
        .digest
        if domain is not None
        else None
    )
    disks = [
        {
            "name": disk.get("name", ""),
            "snapshot": disk.get("snapshot", "default"),
        }
        for disk in document.root.findall("./disks/disk")
    ]
    return ResourceObservation(
        native_id=json.dumps([domain_uuid, snapshot_name], separators=(",", ":")),
        parent_native_id=domain_uuid,
        display_name=snapshot_name,
        status=ResourceStatus.MANAGED,
        persistent_hash=document.fingerprint().digest,
        live_hash=None,
        hash_algorithm=HASH_ALGORITHM,
        details={
            "domain_uuid": domain_uuid,
            "name": snapshot_name,
            "parent_name": document.root.findtext("./parent/name"),
            "current": current,
            "domain_hash": domain_hash,
            "state": document.root.findtext("state") or "unknown",
            "creation_time": creation_time,
            "memory": memory.get("snapshot", "no") if memory is not None else "no",
            "disks": disks,
        },
        documents={"snapshot_xml": content},
    )


def _timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromtimestamp(int(value), tz=UTC)
    except (OverflowError, ValueError) as exc:
        raise XmlStructureError("snapshot creation time is invalid") from exc
    return parsed.isoformat()
