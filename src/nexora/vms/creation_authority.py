"""Authoritative checks for importing one managed volume as a VM."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy import select

from nexora.db import Database
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.host_network_discovery import HostNetworkDiscoveryService
from nexora.resources.libvirt_network_discovery import LibvirtNetworkDiscoveryService
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.storage.usage import StoragePoolUsageGuard
from nexora.storage.volume_contracts import is_attachable_volume
from nexora.vms.creation_contracts import VmCreationOptions, VmImportCreateInput
from nexora.vms.creation_iso_authority import verify_creation_iso, verify_driver_iso


class VmCreationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedImportVolume:
    path: str
    disk_format: str
    architecture: str
    iso_path: str | None
    driver_iso_path: str | None


class VmCreationAuthority:
    def __init__(
        self,
        database: Database,
        storage: StorageDiscoveryService,
        domains: DomainDiscoveryService,
        host_networks: HostNetworkDiscoveryService,
        libvirt_networks: LibvirtNetworkDiscoveryService,
        guard: ResourceWriteGuard,
        architecture: Callable[[str], str],
    ) -> None:
        self.database = database
        self.storage = storage
        self.domains = domains
        self.host_networks = host_networks
        self.libvirt_networks = libvirt_networks
        self.guard = guard
        self.architecture = architecture
        self.usage = StoragePoolUsageGuard(database)

    def refresh_and_verify(self, create: VmImportCreateInput) -> VerifiedImportVolume:
        create.validate()
        self.storage.run(create.host_id)
        self.domains.run(create.host_id)
        self.refresh_options(create)
        pool = self._resource(create.pool_resource_id)
        volume = self._resource(create.volume_resource_id)
        pool_details = json.loads(pool.details_json)
        volume_details = json.loads(volume.details_json)
        self._verify_pool(create, pool, pool_details)
        self._verify_volume(create, volume, volume_details)
        self._verify_unused(create, pool, volume_details)
        self.verify_domain_identity(create)
        self.verify_network(create)
        path = volume_details.get("path")
        disk_format = volume_details.get("format")
        if not isinstance(path, str) or not PurePosixPath(path).is_absolute():
            raise VmCreationConflict("managed volume path is not an absolute path")
        if not is_attachable_volume(volume.display_name, str(disk_format or "")):
            raise VmCreationConflict("managed volume format is not a supported disk image")
        iso_path = verify_creation_iso(self.database, self.guard, create)
        driver_iso_path = verify_driver_iso(self.database, self.guard, create)
        return VerifiedImportVolume(
            path,
            disk_format,
            self.architecture(create.host_id),
            iso_path,
            driver_iso_path,
        )

    def refresh_options(self, create: VmCreationOptions) -> None:
        if create.network_kind == "bridge":
            self.host_networks.run(create.host_id)
        elif create.network_kind == "network":
            self.libvirt_networks.run(create.host_id)

    def _resource(self, resource_id: str) -> ResourceIndex:
        with self.database.session() as session:
            resource = session.get(ResourceIndex, resource_id)
            if resource is None:
                raise VmCreationConflict("VM creation resource no longer exists")
            return resource

    def _verify_pool(
        self,
        create: VmImportCreateInput,
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
            raise VmCreationConflict("storage pool is not writable and active")
        self._verify_base(
            pool,
            ResourceType.STORAGE_POOL,
            create.pool_uuid,
            create.pool_generation,
            create.pool_hash,
        )

    def _verify_volume(
        self,
        create: VmImportCreateInput,
        volume: ResourceIndex,
        details: dict[str, object],
    ) -> None:
        if (
            volume.host_id != create.host_id
            or volume.resource_type != ResourceType.STORAGE_VOLUME
            or volume.native_id != create.volume_native_id
            or volume.parent_native_id != create.pool_uuid
            or volume.display_name != create.volume_name
            or volume.status != ResourceStatus.MANAGED
            or details.get("key") != create.volume_key
            or _integer(details.get("capacity_bytes")) != create.current_capacity_bytes
        ):
            raise VmCreationConflict("storage volume identity or details changed")
        self._verify_base(
            volume,
            ResourceType.STORAGE_VOLUME,
            create.volume_native_id,
            create.volume_generation,
            create.volume_hash,
        )

    def _verify_base(
        self,
        resource: ResourceIndex,
        resource_type: ResourceType,
        native_id: str,
        generation: int,
        persistent_hash: str,
    ) -> None:
        self.guard.verify(
            ResourceBaseVersion(
                resource.id,
                resource.host_id,
                resource_type,
                native_id,
                generation,
                persistent_hash,
                None,
            )
        )

    def _verify_unused(
        self,
        create: VmImportCreateInput,
        pool: ResourceIndex,
        details: dict[str, object],
    ) -> None:
        references = self.usage.volume_references(
            create.host_id,
            pool_name=pool.display_name,
            volume_name=create.volume_name,
            volume_key=create.volume_key,
            volume_path=_text(details.get("path")),
        )
        if references:
            raise VmCreationConflict(f"storage volume is referenced by VM {references[0].vm_name}")

    def verify_domain_identity(self, create: VmCreationOptions) -> None:
        with self.database.session() as session:
            collision = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == create.host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.status != ResourceStatus.MISSING,
                    (
                        (ResourceIndex.native_id == create.vm_uuid)
                        | (ResourceIndex.display_name == create.name)
                    ),
                )
            )
        if collision is not None:
            raise VmCreationConflict("VM name or UUID already exists")

    def verify_network(self, create: VmCreationOptions) -> None:
        if create.network_kind == "none":
            return
        if create.network_resource_id is None:
            raise VmCreationConflict("VM network identity is incomplete")
        network = self._resource(create.network_resource_id)
        details: dict[str, object] = json.loads(network.details_json)
        expected_type = (
            ResourceType.HOST_INTERFACE
            if create.network_kind == "bridge"
            else ResourceType.LIBVIRT_NETWORK
        )
        if (
            network.host_id != create.host_id
            or network.resource_type != expected_type
            or network.native_id != create.network_native_id
            or network.display_name != create.network_name
        ):
            raise VmCreationConflict("VM network identity changed")
        if create.network_kind == "bridge":
            self._verify_bridge(network, details)
        else:
            self._verify_libvirt_network(network, details)
        self.guard.verify(
            ResourceBaseVersion(
                network.id,
                create.host_id,
                expected_type,
                network.native_id,
                int(create.network_generation or 0),
                create.network_hash if create.network_kind == "network" else None,
                create.network_hash if create.network_kind == "bridge" else None,
            )
        )

    def _verify_bridge(
        self,
        network: ResourceIndex,
        details: dict[str, object],
    ) -> None:
        if (
            network.status != ResourceStatus.READ_ONLY
            or details.get("kind") != "bridge"
            or details.get("ifname") != network.display_name
        ):
            raise VmCreationConflict("selected host interface is not a Linux Bridge")

    def _verify_libvirt_network(
        self,
        network: ResourceIndex,
        details: dict[str, object],
    ) -> None:
        if (
            network.status != ResourceStatus.MANAGED
            or not bool(details.get("active"))
            or not bool(details.get("persistent"))
            or details.get("forward_mode") not in {"nat", "isolated"}
        ):
            raise VmCreationConflict("selected libvirt Network is not active and managed")


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else -1
