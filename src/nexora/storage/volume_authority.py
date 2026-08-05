"""Authoritative storage volume identity and VM reference checks."""

import json
from dataclasses import dataclass

from nexora.db import Database
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.storage.usage import StoragePoolUsageGuard, StorageVolumeReference
from nexora.storage.volume_contracts import StorageVolumeMutationInput
from nexora.storage.volume_service import StorageVolumeConflict


@dataclass(frozen=True)
class VerifiedVolume:
    pool: ResourceIndex
    volume: ResourceIndex
    details: dict[str, object]
    current_xml: bytes


class StorageVolumeAuthority:
    def __init__(
        self,
        database: Database,
        storage_discovery: StorageDiscoveryService,
        domain_discovery: DomainDiscoveryService,
        guard: ResourceWriteGuard,
    ) -> None:
        self.database = database
        self.storage_discovery = storage_discovery
        self.domain_discovery = domain_discovery
        self.guard = guard
        self.usage = StoragePoolUsageGuard(database)

    def refresh_and_verify(
        self,
        change: StorageVolumeMutationInput,
        *,
        operation: str,
    ) -> VerifiedVolume:
        self.storage_discovery.run(change.host_id)
        self.domain_discovery.run(change.host_id)
        pool = self._verify_pool(change)
        volume = self._verify_volume(change)
        details: dict[str, object] = json.loads(volume.details_json)
        if details.get("format") not in {"qcow2", "raw"}:
            raise StorageVolumeConflict("storage volume format is not writable")
        references = self.usage.volume_references(
            change.host_id,
            pool_name=pool.display_name,
            volume_name=change.volume_name,
            volume_key=change.volume_key,
            volume_path=_optional_text(details.get("path")),
        )
        self._verify_references(references, operation)
        observation = self.storage_discovery.read_volume(
            change.host_id,
            change.pool_uuid,
            change.volume_key,
        )
        return VerifiedVolume(
            pool,
            volume,
            details,
            observation.documents["volume_xml"],
        )

    def resource(self, resource_id: str) -> ResourceIndex:
        with self.database.session() as session:
            resource = session.get(ResourceIndex, resource_id)
            if resource is None:
                raise StorageVolumeConflict("storage resource no longer exists")
            return resource

    def is_missing(self, change: StorageVolumeMutationInput) -> bool:
        try:
            resource = self.resource(change.volume_resource_id)
        except StorageVolumeConflict:
            return True
        return resource.status == ResourceStatus.MISSING

    def _verify_pool(self, change: StorageVolumeMutationInput) -> ResourceIndex:
        pool = self.resource(change.pool_resource_id)
        details = json.loads(pool.details_json)
        if (
            pool.host_id != change.host_id
            or pool.resource_type != ResourceType.STORAGE_POOL
            or pool.native_id != change.pool_uuid
            or pool.status != ResourceStatus.MANAGED
            or details.get("pool_type") not in {"dir", "netfs"}
            or not bool(details.get("active"))
        ):
            raise StorageVolumeConflict("storage pool is not writable and active")
        self._verify_base(
            pool,
            change,
            ResourceType.STORAGE_POOL,
            change.pool_uuid,
            change.pool_generation,
            change.pool_hash,
        )
        return pool

    def _verify_volume(self, change: StorageVolumeMutationInput) -> ResourceIndex:
        volume = self.resource(change.volume_resource_id)
        if (
            volume.host_id != change.host_id
            or volume.resource_type != ResourceType.STORAGE_VOLUME
            or volume.native_id != change.volume_native_id
            or volume.parent_native_id != change.pool_uuid
            or volume.display_name != change.volume_name
            or volume.status != ResourceStatus.MANAGED
        ):
            raise StorageVolumeConflict("storage volume identity or status changed")
        self._verify_base(
            volume,
            change,
            ResourceType.STORAGE_VOLUME,
            change.volume_native_id,
            change.volume_generation,
            change.volume_hash,
        )
        details = json.loads(volume.details_json)
        if (
            details.get("key") != change.volume_key
            or int(details.get("capacity_bytes", 0)) != change.current_capacity_bytes
        ):
            raise StorageVolumeConflict("storage volume details changed after preview")
        return volume

    def _verify_base(
        self,
        resource: ResourceIndex,
        change: StorageVolumeMutationInput,
        resource_type: ResourceType,
        native_id: str,
        generation: int,
        persistent_hash: str,
    ) -> None:
        self.guard.verify(
            ResourceBaseVersion(
                resource.id,
                change.host_id,
                resource_type,
                native_id,
                generation,
                persistent_hash,
                None,
            )
        )

    def _verify_references(
        self,
        references: list[StorageVolumeReference],
        operation: str,
    ) -> None:
        if operation == "delete" and references:
            raise StorageVolumeConflict(
                f"storage volume is referenced by VM {references[0].vm_name}"
            )
        active = next((item for item in references if item.active), None)
        if operation == "resize" and active is not None:
            raise StorageVolumeConflict(f"active VM {active.vm_name} references the storage volume")


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None
