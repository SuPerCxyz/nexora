"""Authoritative checks for an optional local installation ISO."""

import json
from pathlib import PurePosixPath

from sqlalchemy import select

from nexora.db import Database
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.vms.creation_contracts import VmCreationOptions


class VmCreationIsoConflict(RuntimeError):
    pass


def verify_creation_iso(
    database: Database,
    guard: ResourceWriteGuard,
    create: VmCreationOptions,
) -> str | None:
    if create.iso_resource_id is None:
        return None
    with database.session() as session:
        volume = session.get(ResourceIndex, create.iso_resource_id)
        if volume is None:
            raise VmCreationIsoConflict("installation ISO no longer exists")
        pool = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == create.host_id,
                ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                ResourceIndex.native_id == volume.parent_native_id,
            )
        )
        if pool is None:
            raise VmCreationIsoConflict("installation ISO pool is unavailable")
        details: dict[str, object] = json.loads(volume.details_json)
        pool_details: dict[str, object] = json.loads(pool.details_json)
    if (
        volume.host_id != create.host_id
        or volume.resource_type != ResourceType.STORAGE_VOLUME
        or volume.native_id != create.iso_native_id
        or volume.display_name != create.iso_name
        or volume.status != ResourceStatus.MANAGED
        or details.get("key") != create.iso_key
    ):
        raise VmCreationIsoConflict("installation ISO identity changed")
    path = details.get("path")
    if (
        details.get("format") != "raw"
        or not isinstance(path, str)
        or not PurePosixPath(path).is_absolute()
        or not path.lower().endswith(".iso")
    ):
        raise VmCreationIsoConflict("installation ISO is not a managed raw ISO")
    if (
        pool.status != ResourceStatus.MANAGED
        or pool_details.get("pool_type") not in {"dir", "netfs"}
        or not bool(pool_details.get("active"))
    ):
        raise VmCreationIsoConflict("installation ISO pool is not writable and active")
    guard.verify(
        ResourceBaseVersion(
            volume.id,
            create.host_id,
            ResourceType.STORAGE_VOLUME,
            volume.native_id,
            int(create.iso_generation or 0),
            create.iso_hash,
            None,
        )
    )
    return path


def verify_driver_iso(
    database: Database,
    guard: ResourceWriteGuard,
    create: VmCreationOptions,
) -> str | None:
    if create.driver_iso_resource_id is None:
        return None
    with database.session() as session:
        volume = session.get(ResourceIndex, create.driver_iso_resource_id)
        if volume is None:
            raise VmCreationIsoConflict("driver ISO no longer exists")
        pool = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == create.host_id,
                ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                ResourceIndex.native_id == volume.parent_native_id,
            )
        )
        if pool is None:
            raise VmCreationIsoConflict("driver ISO pool is unavailable")
        details: dict[str, object] = json.loads(volume.details_json)
        pool_details: dict[str, object] = json.loads(pool.details_json)
    if (
        volume.host_id != create.host_id
        or volume.resource_type != ResourceType.STORAGE_VOLUME
        or volume.native_id != create.driver_iso_native_id
        or volume.display_name != create.driver_iso_name
        or volume.status != ResourceStatus.MANAGED
        or details.get("key") != create.driver_iso_key
    ):
        raise VmCreationIsoConflict("driver ISO identity changed")
    path = details.get("path")
    if (
        details.get("format") != "raw"
        or not isinstance(path, str)
        or not PurePosixPath(path).is_absolute()
        or not path.lower().endswith(".iso")
    ):
        raise VmCreationIsoConflict("driver ISO is not a managed raw ISO")
    if (
        pool.status != ResourceStatus.MANAGED
        or pool_details.get("pool_type") not in {"dir", "netfs"}
        or not bool(pool_details.get("active"))
    ):
        raise VmCreationIsoConflict("driver ISO pool is not writable and active")
    guard.verify(
        ResourceBaseVersion(
            volume.id,
            create.host_id,
            ResourceType.STORAGE_VOLUME,
            volume.native_id,
            int(create.driver_iso_generation or 0),
            create.driver_iso_hash,
            None,
        )
    )
    return path
