"""Bounded local reads for storage management pages."""

import json
from dataclasses import dataclass

from sqlalchemy import select

from nexora.db import Database
from nexora.hosts.models import Host, HostStatus
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType


@dataclass(frozen=True)
class StoragePoolView:
    host: Host
    pool: ResourceIndex
    details: dict[str, object]


@dataclass(frozen=True)
class StorageVolumeView:
    host: Host
    pool: ResourceIndex
    volume: ResourceIndex
    details: dict[str, object]


class StorageReadService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def hosts(self, *, limit: int = 500) -> list[Host]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(Host)
                    .where(Host.status == HostStatus.READY)
                    .order_by(Host.name)
                    .limit(limit)
                )
            )

    def pools(self, *, limit: int = 5_000) -> list[StoragePoolView]:
        if not 1 <= limit <= 5_000:
            raise ValueError("invalid storage pool result limit")
        with self.database.session() as session:
            rows = session.execute(
                select(Host, ResourceIndex)
                .join(ResourceIndex, ResourceIndex.host_id == Host.id)
                .where(
                    ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                    ResourceIndex.status != ResourceStatus.MISSING,
                )
                .order_by(Host.name, ResourceIndex.display_name)
                .limit(limit)
            )
            return [
                StoragePoolView(host, pool, json.loads(pool.details_json)) for host, pool in rows
            ]

    def pool(self, resource_id: str) -> StoragePoolView | None:
        with self.database.session() as session:
            row = session.execute(
                select(Host, ResourceIndex)
                .join(ResourceIndex, ResourceIndex.host_id == Host.id)
                .where(
                    ResourceIndex.id == resource_id,
                    ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                    ResourceIndex.status == ResourceStatus.MANAGED,
                )
            ).one_or_none()
            if row is None:
                return None
            host, pool = row
            return StoragePoolView(host, pool, json.loads(pool.details_json))

    def volumes(self, *, limit: int = 10_000) -> list[StorageVolumeView]:
        if not 1 <= limit <= 10_000:
            raise ValueError("invalid storage volume result limit")
        with self.database.session() as session:
            volumes = list(
                session.scalars(
                    select(ResourceIndex)
                    .where(
                        ResourceIndex.resource_type == ResourceType.STORAGE_VOLUME,
                        ResourceIndex.status != ResourceStatus.MISSING,
                    )
                    .order_by(ResourceIndex.host_id, ResourceIndex.display_name)
                    .limit(limit)
                )
            )
            host_ids = {volume.host_id for volume in volumes}
            parent_ids = {
                volume.parent_native_id for volume in volumes if volume.parent_native_id is not None
            }
            hosts = {
                host.id: host for host in session.scalars(select(Host).where(Host.id.in_(host_ids)))
            }
            pools = {
                (pool.host_id, pool.native_id): pool
                for pool in session.scalars(
                    select(ResourceIndex).where(
                        ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                        ResourceIndex.native_id.in_(parent_ids),
                    )
                )
            }
            return [
                StorageVolumeView(
                    hosts[volume.host_id],
                    pools[(volume.host_id, str(volume.parent_native_id))],
                    volume,
                    json.loads(volume.details_json),
                )
                for volume in volumes
                if volume.host_id in hosts
                and (volume.host_id, str(volume.parent_native_id)) in pools
            ]

    def volume(self, resource_id: str) -> StorageVolumeView | None:
        return next(
            (view for view in self.volumes() if view.volume.id == resource_id),
            None,
        )
