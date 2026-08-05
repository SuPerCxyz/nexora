"""Copied Volume and final Domain verification for platform-image VM creation."""

import json
from pathlib import PurePosixPath

from sqlalchemy import select

from nexora.db import Database
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.vms.creation_verify import created_vm_matches
from nexora.vms.media_creation_contracts import VmMediaCreateInput
from nexora.xml import LibvirtXmlDocument


class MediaCreationVerificationError(RuntimeError):
    pass


class MediaCreationVerifier:
    def __init__(self, database: Database) -> None:
        self.database = database

    def copied_volume(
        self,
        create: VmMediaCreateInput,
        path: str,
    ) -> None:
        details = self._volume_details(
            create,
            create.target_file_name,
            "copied image was not discovered as a managed Volume",
        )
        if (
            details.get("path") != path
            or details.get("format") != create.media_format
            or details.get("backing_path") is not None
        ):
            raise MediaCreationVerificationError(
                "copied Volume identity or backing chain is unsafe"
            )

    def seed_volume(self, create: VmMediaCreateInput, path: str | None) -> None:
        if path is None:
            return
        details = self._volume_details(
            create,
            PurePosixPath(path).name,
            "cloud-init seed was not discovered as a Volume",
        )
        if details.get("path") != path or details.get("format") not in {"iso", "raw"}:
            raise MediaCreationVerificationError("cloud-init seed Volume identity is invalid")

    def vm_matches(
        self,
        resource: ResourceIndex,
        create: VmMediaCreateInput,
        xml: bytes,
    ) -> bool:
        document = LibvirtXmlDocument.parse(xml, expected_root="domain")
        disk_path = self.disk_path(xml)
        iso_path = _device_source(document, "sda")
        cloud_path = _device_source(document, "sdb")
        details: dict[str, object] = json.loads(resource.details_json)
        return (
            resource.display_name == create.name
            and disk_path is not None
            and created_vm_matches(
                details,
                create,
                disk_path=disk_path,
                iso_path=iso_path or "",
                cloud_init_path=cloud_path or "",
            )
        )

    def disk_path(self, xml: bytes) -> str:
        document = LibvirtXmlDocument.parse(xml, expected_root="domain")
        path = _device_source(document, "vda")
        if path is None:
            raise MediaCreationVerificationError("planned system disk path is unavailable")
        return path

    def _volume_details(
        self,
        create: VmMediaCreateInput,
        name: str,
        missing_message: str,
    ) -> dict[str, object]:
        with self.database.session() as session:
            volume = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == create.host_id,
                    ResourceIndex.resource_type == ResourceType.STORAGE_VOLUME,
                    ResourceIndex.parent_native_id == create.pool_uuid,
                    ResourceIndex.display_name == name,
                )
            )
            if volume is None or volume.status != ResourceStatus.MANAGED:
                raise MediaCreationVerificationError(missing_message)
            parsed: object = json.loads(volume.details_json)
            if not isinstance(parsed, dict):
                raise MediaCreationVerificationError("Volume metadata is invalid")
            return {str(key): value for key, value in parsed.items()}


def _device_source(document: LibvirtXmlDocument, target_name: str) -> str | None:
    for disk in document.root.findall("./devices/disk"):
        target = disk.find("target")
        source = disk.find("source")
        if target is not None and target.get("dev") == target_name and source is not None:
            return source.get("file")
    return None
