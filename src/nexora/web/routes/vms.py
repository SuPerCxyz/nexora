"""Node-scoped virtual machine pages and lifecycle task submission."""

from uuid import uuid4

from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy import select
from starlette.responses import Response

from nexora.auth.sessions import SessionIdentity, SessionService
from nexora.media.models import MediaKind, MediaStatus
from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.storage.read_service import StorageReadService
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.read_service import TaskReadService
from nexora.vms.contracts import LifecycleAction, LifecycleTaskInput
from nexora.vms.read_service import VmReadService
from nexora.web.rendering import templates
from nexora.web.security import CSRF_COOKIE, SESSION_COOKIE
from nexora.xml import (
    AdvancedConfig,
    CpuTopologyChange,
    LibvirtXmlDocument,
    MemoryConfigChange,
    read_advanced_config,
    read_cpu_topology,
    read_memory_config,
)
from nexora.xml.errors import CpuTopologyError, XmlSafetyError, XmlStructureError

router = APIRouter(include_in_schema=False)
DANGEROUS_ACTIONS = frozenset({LifecycleAction.FORCE_OFF, LifecycleAction.FORCE_REBOOT})


@router.get("/vms")
async def vm_list(request: Request) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="vms/list.html",
        context={
            "administrator": identity,
            "csrf_token": _csrf(request),
            "vms": VmReadService(request.app.state.database).list_vms(),
        },
    )


@router.get("/hosts/{host_id}/vms/{domain_uuid}")
@router.get("/manage/hosts/{host_id}/vms/{domain_uuid}")
async def vm_detail(request: Request, host_id: str, domain_uuid: str) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    try:
        read_service = VmReadService(request.app.state.database)
        detail = read_service.detail(host_id, domain_uuid)
    except ValueError:
        detail = None
    if detail is None:
        return PlainTextResponse("Virtual machine not found", status_code=404)
    volumes = StorageReadService(request.app.state.database).volumes()
    storage_volumes = [
        view
        for view in volumes
        if view.host.id == host_id
        and view.volume.status == "managed"
        and view.details.get("format") in {"qcow2", "raw"}
        and not view.volume.display_name.lower().endswith(".iso")
    ]
    local_isos = [
        view
        for view in volumes
        if view.host.id == host_id
        and view.volume.status == "managed"
        and view.details.get("format") == "raw"
        and view.volume.display_name.lower().endswith(".iso")
        and str(view.details.get("path", "")).lower().endswith(".iso")
    ]
    platform_isos = [
        item
        for item in request.app.state.media_index_store.list_items()
        if item.kind == MediaKind.ISO and item.status == MediaStatus.AVAILABLE
    ]
    clone_pools = [
        pool
        for pool in StorageReadService(request.app.state.database).pools()
        if pool.pool.status == "managed"
        and pool.details.get("pool_type") in {"dir", "netfs"}
        and pool.details.get("active")
    ]
    with request.app.state.database.session() as session:
        host_devices = list(
            session.scalars(
                select(ResourceIndex)
                .where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type.in_(
                        [ResourceType.PCI_DEVICE, ResourceType.USB_DEVICE]
                    ),
                    ResourceIndex.status != "missing",
                )
                .order_by(ResourceIndex.resource_type, ResourceIndex.display_name)
            )
        )
    return templates.TemplateResponse(
        request=request,
        name="vms/detail.html",
        context={
            "administrator": identity,
            "csrf_token": _csrf(request),
            "vm": detail,
            "cpu_topology": _cpu_topology(detail.documents.get("persistent_xml")),
            "memory_config": _memory_config(detail.documents.get("persistent_xml")),
            "advanced_config": _advanced_config(detail.documents.get("persistent_xml")),
            "formatted_xml": _formatted_xml(detail.documents),
            "storage_volumes": storage_volumes,
            "local_isos": local_isos,
            "platform_isos": platform_isos,
            "clone_pools": clone_pools,
            "snapshots": read_service.snapshots(host_id, domain_uuid),
            "platform_iso_enabled": request.app.state.settings.media_public_base_url is not None,
            "host_devices": host_devices,
            "shared_directory_roots": list(
                enumerate(request.app.state.settings.shared_directory_root_list)
            ),
        },
    )


@router.post("/hosts/{host_id}/vms/{domain_uuid}/lifecycle")
async def vm_lifecycle_submit(
    request: Request,
    host_id: str,
    domain_uuid: str,
) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    try:
        action = LifecycleAction(str(form.get("action", "")))
        detail = VmReadService(request.app.state.database).detail(host_id, domain_uuid)
        if detail is None:
            return PlainTextResponse("Virtual machine not found", status_code=404)
        if (
            action in DANGEROUS_ACTIONS
            and str(form.get("confirmation_name", "")) != detail.resource.display_name
        ):
            return PlainTextResponse("VM name confirmation does not match", status_code=409)
        base = ResourceBaseVersion(
            resource_id=str(form.get("resource_id", "")),
            host_id=host_id,
            resource_type=ResourceType.VIRTUAL_MACHINE,
            native_id=detail.resource.native_id,
            generation=int(str(form.get("generation", "0"))),
            persistent_hash=_optional_hash(form.get("persistent_hash")),
            live_hash=_optional_hash(form.get("live_hash")),
        )
        if base.resource_id != detail.resource.id or base.generation < 1:
            raise ValueError("VM base version is invalid")
    except (TypeError, ValueError):
        return PlainTextResponse("VM lifecycle request is invalid", status_code=422)
    active = TaskReadService(request.app.state.database).find_active_vm_write(
        host_id,
        detail.resource.native_id,
    )
    if active is not None:
        return RedirectResponse(f"/tasks/{active.id}", status_code=status.HTTP_303_SEE_OTHER)
    task_input = LifecycleTaskInput(action, base)
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.lifecycle",
            title=f"{action.value} · {detail.resource.display_name}",
            idempotency_scope=f"vm:{host_id}:{detail.resource.native_id}:lifecycle",
            idempotency_key=str(uuid4()),
            host_id=host_id,
            vm_uuid=detail.resource.native_id,
            resource_type=ResourceType.VIRTUAL_MACHINE,
            resource_id=detail.resource.id,
            total_steps=3,
            resumable=False,
            recovery_strategy="verify_only",
            input_summary=task_input.encode(),
        )
    )
    return RedirectResponse(f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


def _identity(request: Request) -> SessionIdentity | None:
    service: SessionService = request.app.state.session_service
    return service.resolve(request.cookies.get(SESSION_COOKIE))


def _csrf(request: Request) -> str:
    return request.cookies.get(CSRF_COOKIE, "")


def _valid_csrf(request: Request, submitted: object) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    service: SessionService = request.app.state.session_service
    return (
        token is not None and isinstance(submitted, str) and service.verify_csrf(token, submitted)
    )


def _optional_hash(value: object) -> str | None:
    text = str(value or "")
    if not text:
        return None
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError("invalid resource hash")
    return text


def _cpu_topology(content: str | None) -> CpuTopologyChange | None:
    if content is None:
        return None
    try:
        document = LibvirtXmlDocument.parse(content.encode(), expected_root="domain")
        return read_cpu_topology(document)
    except (CpuTopologyError, XmlSafetyError, XmlStructureError):
        return None


def _memory_config(content: str | None) -> MemoryConfigChange | None:
    if content is None:
        return None
    try:
        document = LibvirtXmlDocument.parse(content.encode(), expected_root="domain")
        return read_memory_config(document)
    except (XmlSafetyError, XmlStructureError):
        return None


def _advanced_config(content: str | None) -> AdvancedConfig | None:
    if content is None:
        return None
    try:
        document = LibvirtXmlDocument.parse(content.encode(), expected_root="domain")
        return read_advanced_config(document)
    except (XmlSafetyError, XmlStructureError):
        return None


def _formatted_xml(documents: dict[str, str]) -> str:
    raw = documents.get("persistent_xml") or documents.get("live_xml") or ""
    if not raw:
        return ""
    try:
        from lxml import etree

        tree = etree.fromstring(raw.encode())
        return etree.tostring(tree, pretty_print=True, encoding="unicode")
    except Exception:
        return raw
