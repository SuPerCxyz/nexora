"""VM configuration data for the authenticated React application."""

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select

from nexora.media.models import MediaKind, MediaStatus
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.storage.read_service import StorageReadService
from nexora.vms.read_service import VmReadService
from nexora.web.internal.auth import internal_error, no_store, resolve_internal_identity
from nexora.web.routes.vms import _advanced_config, _cpu_topology, _memory_config

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.get("/hosts/{host_id}/vms/{domain_uuid}/configuration")
async def vm_configuration(request: Request, host_id: str, domain_uuid: str) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    try:
        detail = VmReadService(request.app.state.database).detail(host_id, domain_uuid)
    except ValueError:
        detail = None
    if detail is None:
        return internal_error(404, "vm_not_found", "虚拟机不存在")
    persistent_xml = detail.documents.get("persistent_xml")
    cpu = _cpu_topology(persistent_xml)
    memory = _memory_config(persistent_xml)
    advanced = _advanced_config(persistent_xml)
    payload = {
        "vm": {
            "name": detail.resource.display_name,
            "host_id": host_id,
            "native_id": detail.resource.native_id,
            "state": str(detail.details.get("state", detail.resource.status)),
            "active": bool(detail.details.get("active", False)),
            "persistent": bool(detail.details.get("persistent", False)),
        },
        "base": {
            "resource_id": detail.resource.id,
            "generation": detail.resource.observed_generation,
            "persistent_hash": detail.resource.persistent_hash,
        },
        "cpu": asdict(cpu) if cpu is not None else None,
        "memory": asdict(memory) if memory is not None else None,
        "advanced": asdict(advanced) if advanced is not None else None,
        "disks": detail.details.get("disks", []),
        "interfaces": detail.details.get("interfaces", []),
        "networks": _networks(request, host_id),
        "storage_volumes": _storage_volumes(request, host_id),
        "platform_isos": [
            {
                "id": item.id,
                "name": item.file_name,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for item in request.app.state.media_index_store.list_items()
            if item.kind == MediaKind.ISO and item.status == MediaStatus.AVAILABLE
        ],
        "platform_iso_enabled": request.app.state.settings.media_public_base_url is not None,
        "host_devices": _host_devices(request, host_id),
        "shared_directory_roots": list(request.app.state.settings.shared_directory_root_list),
    }
    return no_store(JSONResponse(jsonable_encoder(payload)))


def _storage_volumes(request: Request, host_id: str) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for view in StorageReadService(request.app.state.database).volumes():
        if view.host.id != host_id or view.volume.status != "managed":
            continue
        values.append(
            {
                "resource_id": view.volume.id,
                "native_id": view.volume.native_id,
                "name": view.volume.display_name,
                "generation": view.volume.observed_generation,
                "persistent_hash": view.volume.persistent_hash,
                "pool_name": view.pool.display_name,
                "format": view.details.get("format"),
                "path": view.details.get("path"),
                "capacity_bytes": view.details.get("capacity_bytes"),
            }
        )
    return values


def _networks(request: Request, host_id: str) -> list[dict[str, object]]:
    from nexora.web.routes.vm_create_options import eligible_networks

    return [
        {
            "resource_id": item.resource.id,
            "kind": item.kind,
            "name": item.resource.display_name,
        }
        for item in eligible_networks(request.app.state.database)
        if item.host.id == host_id
    ]


def _host_devices(request: Request, host_id: str) -> list[dict[str, object]]:
    with request.app.state.database.session() as session:
        resources = list(
            session.scalars(
                select(ResourceIndex)
                .where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type.in_(
                        (ResourceType.PCI_DEVICE, ResourceType.USB_DEVICE)
                    ),
                    ResourceIndex.status != "missing",
                )
                .order_by(ResourceIndex.resource_type, ResourceIndex.display_name)
            )
        )
    return [
        {
            "resource_id": item.id,
            "type": item.resource_type,
            "name": item.display_name,
            "address": item.native_id,
            "status": item.status,
        }
        for item in resources
    ]
