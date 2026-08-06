"""Bounded ResourceIndex options for the VM creation form."""

import json
from dataclasses import dataclass

from sqlalchemy import select

from nexora.db import Database
from nexora.hosts.models import Host
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.storage.read_service import StorageReadService, StorageVolumeView
from nexora.storage.usage import StoragePoolUsageGuard
from nexora.storage.volume_contracts import is_attachable_volume


@dataclass(frozen=True)
class NetworkOption:
    host: Host
    resource: ResourceIndex
    kind: str


def eligible_volumes(database: Database) -> list[StorageVolumeView]:
    usage = StoragePoolUsageGuard(database)
    return [
        view
        for view in StorageReadService(database).volumes()
        if view.volume.status == ResourceStatus.MANAGED
        and view.pool.status == ResourceStatus.MANAGED
        and view.pool.persistent_hash is not None
        and view.volume.persistent_hash is not None
        and is_attachable_volume(
            view.volume.display_name, str(view.details.get("format") or "")
        )
        and view.details.get("capacity_bytes", 0)
        and not usage.volume_references(
            view.host.id,
            pool_name=view.pool.display_name,
            volume_name=view.volume.display_name,
            volume_key=str(view.details.get("key", "")),
            volume_path=_optional_text(view.details.get("path")),
        )
    ]


def eligible_isos(database: Database) -> list[StorageVolumeView]:
    return [view for view in StorageReadService(database).volumes() if _is_iso_view(view)]


def eligible_networks(database: Database) -> list[NetworkOption]:
    with database.session() as session:
        rows = session.execute(
            select(Host, ResourceIndex)
            .join(ResourceIndex, ResourceIndex.host_id == Host.id)
            .where(
                ResourceIndex.resource_type.in_(
                    (ResourceType.HOST_INTERFACE, ResourceType.LIBVIRT_NETWORK)
                ),
                ResourceIndex.status != ResourceStatus.MISSING,
            )
            .order_by(Host.name, ResourceIndex.display_name)
        )
        result = []
        for host, resource in rows:
            details: dict[str, object] = json.loads(resource.details_json)
            kind = _network_kind(resource, details)
            if kind is not None:
                result.append(NetworkOption(host, resource, kind))
        return result


def network_identity(
    database: Database,
    host_id: str,
    resource_id: str,
) -> tuple[str, str | None, str | None, int | None, str | None, str | None]:
    if not resource_id:
        return ("none", None, None, None, None, None)
    with database.session() as session:
        resource = session.get(ResourceIndex, resource_id)
        if resource is None or resource.host_id != host_id:
            raise ValueError("Selected VM network is outside the target host")
        details: dict[str, object] = json.loads(resource.details_json)
        kind = _network_kind(resource, details)
        if kind is None:
            raise ValueError("Selected VM network is not eligible")
        network_hash = resource.live_hash if kind == "bridge" else resource.persistent_hash
        return (
            kind,
            resource.id,
            resource.native_id,
            resource.observed_generation,
            network_hash,
            resource.display_name,
        )


def iso_identity(
    database: Database,
    host_id: str,
    resource_id: str,
) -> tuple[str | None, str | None, int | None, str | None, str | None, str | None]:
    if not resource_id:
        return (None, None, None, None, None, None)
    view = StorageReadService(database).volume(resource_id)
    if view is None or view.host.id != host_id or not _is_iso_view(view):
        raise ValueError("Selected installation ISO is not eligible for the target host")
    key = view.details.get("key")
    if not isinstance(key, str):
        raise ValueError("Selected installation ISO metadata is incomplete")
    return (
        view.volume.id,
        view.volume.native_id,
        view.volume.observed_generation,
        view.volume.persistent_hash,
        key,
        view.volume.display_name,
    )


def _is_iso_view(view: StorageVolumeView) -> bool:
    return (
        view.volume.status == ResourceStatus.MANAGED
        and view.pool.status == ResourceStatus.MANAGED
        and view.volume.persistent_hash is not None
        and view.details.get("format") == "raw"
        and view.volume.display_name.lower().endswith(".iso")
        and str(view.details.get("path", "")).lower().endswith(".iso")
    )


def _network_kind(
    resource: ResourceIndex,
    details: dict[str, object],
) -> str | None:
    if (
        resource.resource_type == ResourceType.HOST_INTERFACE
        and resource.status == ResourceStatus.READ_ONLY
        and resource.live_hash is not None
        and details.get("kind") == "bridge"
    ):
        return "bridge"
    if (
        resource.resource_type == ResourceType.LIBVIRT_NETWORK
        and resource.status == ResourceStatus.MANAGED
        and resource.persistent_hash is not None
        and bool(details.get("active"))
        and bool(details.get("persistent"))
        and details.get("forward_mode") in {"nat", "isolated"}
    ):
        return "network"
    return None


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None
