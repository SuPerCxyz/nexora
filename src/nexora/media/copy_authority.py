"""Authoritative resource guard for platform image copy writes."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from nexora.db import Database
from nexora.hosts.models import Host
from nexora.media.copy_contracts import MediaCopyInput
from nexora.media.models import MediaItem, MediaKind, MediaStatus
from nexora.resources.conflicts import (
    ResourceBaseVersion,
    ResourceWriteConflict,
    ResourceWriteGuard,
)
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.tasks.locks import ResourceLockStore


class MediaCopyAuthorityError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedCopyResources:
    media: MediaItem
    pool: ResourceIndex
    host: Host


class MediaCopyAuthority:
    def __init__(
        self,
        database: Database,
        discovery: StorageDiscoveryService,
        store: ResourceIndexStore,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
    ) -> None:
        self.database = database
        self.discovery = discovery
        self.store = store
        self.guard = guard
        self.locks = locks

    @contextmanager
    def verify(
        self,
        copy_input: MediaCopyInput,
        task_id: str,
    ) -> Iterator[VerifiedCopyResources]:
        media, _pool, host = self._cached_resources(copy_input)
        self.locks.acquire(
            copy_input.host_id,
            ResourceType.STORAGE_POOL,
            copy_input.pool_native_id,
            task_id,
        )
        try:
            observation = self.discovery.read_pool(
                copy_input.host_id,
                copy_input.pool_native_id,
            )
            refreshed = self.store.refresh_one(
                copy_input.host_id,
                ResourceType.STORAGE_POOL,
                observation,
            )
            try:
                self.guard.verify(_base_version(copy_input))
            except ResourceWriteConflict as exc:
                raise MediaCopyAuthorityError(exc.reason) from exc
            if refreshed.status != ResourceStatus.MANAGED:
                raise MediaCopyAuthorityError("target storage pool is not writable")
            yield VerifiedCopyResources(media, refreshed, host)
        finally:
            self.locks.release(
                copy_input.host_id,
                ResourceType.STORAGE_POOL,
                copy_input.pool_native_id,
                task_id,
            )

    def _cached_resources(
        self,
        copy_input: MediaCopyInput,
    ) -> tuple[MediaItem, ResourceIndex, Host]:
        with self.database.session() as session:
            media = session.get(MediaItem, copy_input.media_item_id)
            pool = session.get(ResourceIndex, copy_input.pool_resource_id)
            host = session.get(Host, copy_input.host_id)
            if (
                media is None
                or media.status != MediaStatus.AVAILABLE
                or media.kind not in {MediaKind.QCOW2, MediaKind.RAW}
                or media.sha256 != copy_input.media_sha256
            ):
                raise MediaCopyAuthorityError("source image changed or is unavailable")
            if (
                pool is None
                or host is None
                or pool.host_id != host.id
                or pool.resource_type != ResourceType.STORAGE_POOL
                or pool.status != ResourceStatus.MANAGED
                or pool.native_id != copy_input.pool_native_id
                or pool.observed_generation != copy_input.pool_generation
                or pool.persistent_hash != copy_input.pool_persistent_hash
            ):
                raise MediaCopyAuthorityError("target storage pool changed or is unavailable")
            return media, pool, host


def _base_version(copy_input: MediaCopyInput) -> ResourceBaseVersion:
    return ResourceBaseVersion(
        resource_id=copy_input.pool_resource_id,
        host_id=copy_input.host_id,
        resource_type=ResourceType.STORAGE_POOL,
        native_id=copy_input.pool_native_id,
        generation=copy_input.pool_generation,
        persistent_hash=copy_input.pool_persistent_hash,
        live_hash=None,
    )
