"""Authoritative-cache guard for storage pools referenced by VMs."""

import json
from dataclasses import dataclass

from sqlalchemy import select

from nexora.db import Database
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType


class StoragePoolInUseError(RuntimeError):
    pass


@dataclass(frozen=True)
class StorageVolumeReference:
    vm_name: str
    state: str

    @property
    def active(self) -> bool:
        return self.state.lower() not in {"shut off", "shutoff"}


class StoragePoolUsageGuard:
    def __init__(self, database: Database) -> None:
        self.database = database

    def ensure_not_in_use(
        self,
        host_id: str,
        pool_name: str,
        target_path: object,
    ) -> None:
        target = target_path if isinstance(target_path, str) else None
        with self.database.session() as session:
            domains = session.scalars(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.status != ResourceStatus.MISSING,
                )
            )
            for domain in domains:
                details = json.loads(domain.details_json)
                for disk in details.get("disks", []):
                    source = disk.get("source")
                    path_match = (
                        target is not None
                        and isinstance(source, str)
                        and (source == target or source.startswith(target + "/"))
                    )
                    if path_match or disk.get("pool") == pool_name:
                        raise StoragePoolInUseError(
                            f"storage pool is referenced by VM {domain.display_name}"
                        )

    def volume_references(
        self,
        host_id: str,
        *,
        pool_name: str,
        volume_name: str,
        volume_key: str,
        volume_path: str | None,
    ) -> list[StorageVolumeReference]:
        references: list[StorageVolumeReference] = []
        with self.database.session() as session:
            domains = session.scalars(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.status != ResourceStatus.MISSING,
                )
            )
            for domain in domains:
                details = json.loads(domain.details_json)
                for disk in details.get("disks", []):
                    source = disk.get("source")
                    pool_match = disk.get("pool") == pool_name and source == volume_name
                    if source in {volume_key, volume_path} or pool_match:
                        references.append(
                            StorageVolumeReference(
                                domain.display_name,
                                str(details.get("state", "unknown")),
                            )
                        )
                        break
        return references
