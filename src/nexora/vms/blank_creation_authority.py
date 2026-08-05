"""Authoritative guards for blank-disk VM creation."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy import select

from nexora.db import Database
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.storage.usage import StoragePoolUsageGuard
from nexora.vms.blank_creation_contracts import VmBlankCreateInput
from nexora.vms.creation_authority import VmCreationAuthority
from nexora.vms.creation_iso_authority import verify_creation_iso, verify_driver_iso


class VmBlankCreationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedBlankDisk:
    disk_path: str
    disk_format: str
    architecture: str
    iso_path: str | None
    driver_iso_path: str | None


class VmBlankCreationAuthority:
    def __init__(
        self,
        database: Database,
        storage: StorageDiscoveryService,
        options: VmCreationAuthority,
        guard: ResourceWriteGuard,
        architecture: Callable[[str], str],
    ) -> None:
        self.database = database
        self.storage = storage
        self.options = options
        self.guard = guard
        self._architecture = architecture

    def refresh_and_verify(self, create: VmBlankCreateInput) -> VerifiedBlankDisk:
        create.validate()
        self.storage.run(create.host_id)
        self.options.domains.run(create.host_id)
        self.options.refresh_options(create)
        pool = self._pool(create.pool_resource_id)
        details: dict[str, object] = json.loads(pool.details_json)
        self._verify_pool(create, pool, details)
        self._verify_disk_unused(create, pool, details)
        self.options.verify_domain_identity(create)
        self.options.verify_network(create)
        iso_path = verify_creation_iso(self.database, self.guard, create)
        driver_iso_path = verify_driver_iso(self.database, self.guard, create)
        disk_path = _target_directory(details) / create.disk_name
        architecture = str(self._architecture(create.host_id))
        if architecture not in {"x86_64", "aarch64"}:
            raise VmBlankCreationConflict("host architecture is not supported")
        return VerifiedBlankDisk(
            str(disk_path),
            create.volume_format,
            architecture,
            iso_path,
            driver_iso_path,
        )

    def _pool(self, resource_id: str) -> ResourceIndex:
        with self.database.session() as session:
            pool = session.get(ResourceIndex, resource_id)
            if pool is None:
                raise VmBlankCreationConflict("target storage pool no longer exists")
            session.expunge(pool)
            return pool

    def _verify_pool(
        self,
        create: VmBlankCreateInput,
        pool: ResourceIndex,
        details: dict[str, object],
    ) -> None:
        if (
            pool.host_id != create.host_id
            or pool.resource_type != ResourceType.STORAGE_POOL
            or pool.native_id != create.pool_uuid
            or pool.status != ResourceStatus.MANAGED
            or details.get("pool_type") not in {"dir", "netfs"}
            or not bool(details.get("active"))
        ):
            raise VmBlankCreationConflict("storage pool is not writable and active")
        self.guard.verify(
            ResourceBaseVersion(
                pool.id,
                create.host_id,
                ResourceType.STORAGE_POOL,
                create.pool_uuid,
                create.pool_generation,
                create.pool_hash,
                None,
            )
        )

    def _verify_disk_unused(
        self,
        create: VmBlankCreateInput,
        pool: ResourceIndex,
        details: dict[str, object],
    ) -> None:
        with self.database.session() as session:
            existing = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == create.host_id,
                    ResourceIndex.resource_type == ResourceType.STORAGE_VOLUME,
                    ResourceIndex.parent_native_id == create.pool_uuid,
                    ResourceIndex.display_name == create.disk_name,
                    ResourceIndex.status != ResourceStatus.MISSING,
                )
            )
        if existing is not None:
            raise VmBlankCreationConflict(
                f"storage volume {create.disk_name} already exists in the pool"
            )
        references = StoragePoolUsageGuard(self.database).volume_references(
            create.host_id,
            pool_name=pool.display_name,
            volume_name=create.disk_name,
            volume_key=create.disk_name,
            volume_path=str(_target_directory(details)),
        )
        if references:
            raise VmBlankCreationConflict(
                f"storage volume is referenced by VM {references[0].vm_name}"
            )


def _target_directory(details: dict[str, object]) -> PurePosixPath:
    value = details.get("target_path")
    path = PurePosixPath(value) if isinstance(value, str) else PurePosixPath(".")
    if (
        not isinstance(value, str)
        or not path.is_absolute()
        or ".." in path.parts
        or path == PurePosixPath("/")
    ):
        raise VmBlankCreationConflict("target storage pool path is not path-safe")
    return path
