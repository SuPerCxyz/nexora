"""Platform-image VM creation preview, confirmation, and task submission."""

import json
import secrets
from collections.abc import Mapping
from typing import cast
from uuid import uuid4

from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from nexora.auth.sessions import SessionIdentity, SessionService
from nexora.media.copy_read import MediaCopyTarget, MediaCopyTargetService
from nexora.media.models import MediaItem, MediaKind, MediaStatus
from nexora.resources.models import ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.models import Task
from nexora.vms.cloud_password import hash_guest_password
from nexora.vms.media_creation_authority import VmMediaCreationConflict
from nexora.vms.media_creation_contracts import VmMediaCreateInput
from nexora.vms.media_creation_models import VmMediaCreationPlan
from nexora.vms.media_creation_service import VmMediaCreationError, VmMediaCreationService
from nexora.vms.media_creation_tasks import VmMediaCreationTaskInput
from nexora.web.rendering import templates
from nexora.web.routes.vm_create_options import (
    eligible_isos,
    eligible_networks,
    iso_identity,
    network_identity,
)
from nexora.web.security import CSRF_COOKIE, SESSION_COOKIE

router = APIRouter(include_in_schema=False)


@router.get("/vms/create/platform-image")
async def vm_media_create_form(request: Request) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="vms/create_media.html",
        context={
            "administrator": identity,
            "csrf_token": _csrf(request),
            "media_items": eligible_media(request),
            "targets": MediaCopyTargetService(request.app.state.database).list_targets(),
            "networks": eligible_networks(request.app.state.database),
            "isos": eligible_isos(request.app.state.database),
        },
    )


@router.post("/vms/create/platform-image/preview")
async def vm_media_create_preview(request: Request) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    item = request.app.state.media_index_store.get_item(str(form.get("media_item_id", "")))
    target = media_target(request, str(form.get("pool_resource_id", "")))
    if item is None or target is None:
        return PlainTextResponse("Platform image or target Pool not found", status_code=404)
    try:
        create = await run_in_threadpool(build_vm_media_create_input, request, item, target, form)
        service: VmMediaCreationService = request.app.state.vm_media_creation_service
        preview = await run_in_threadpool(service.preview, create)
    except (TypeError, ValueError, RuntimeError, VmMediaCreationError) as exc:
        return PlainTextResponse(str(exc), status_code=422)
    return templates.TemplateResponse(
        request=request,
        name="vms/create_media_preview.html",
        context={
            "administrator": identity,
            "csrf_token": _csrf(request),
            "preview": preview,
            "create": create,
            "item": item,
            "target": target,
        },
    )


@router.post("/vms/create/platform-image/apply")
async def vm_media_create_apply(request: Request) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    service: VmMediaCreationService = request.app.state.vm_media_creation_service
    try:
        plan = await run_in_threadpool(
            service.confirm,
            str(form.get("plan_id", "")),
            str(form.get("confirmation_token", "")),
            host_id=str(form.get("host_id", "")),
            vm_uuid=str(form.get("vm_uuid", "")),
        )
    except (VmMediaCreationError, VmMediaCreationConflict) as exc:
        return PlainTextResponse(str(exc), status_code=409)
    task = enqueue_vm_media_creation(request, plan)
    return RedirectResponse(f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


def enqueue_vm_media_creation(request: Request, plan: VmMediaCreationPlan) -> Task:
    task_input = VmMediaCreationTaskInput(plan.id, plan.host_id, plan.vm_uuid)
    return cast(
        Task,
        request.app.state.task_queue.enqueue(
            TaskCreate(
                task_type="vm.create_from_media",
                title=f"从平台镜像创建虚拟机 · {plan.vm_name}",
                idempotency_scope=f"host:{plan.host_id}:vm:{plan.vm_uuid}:media-create",
                idempotency_key=plan.id,
                host_id=plan.host_id,
                vm_uuid=plan.vm_uuid,
                resource_type=ResourceType.VIRTUAL_MACHINE,
                resource_id=plan.vm_uuid,
                total_steps=5,
                resumable=True,
                max_retries=3,
                recovery_strategy="resume_from_checkpoint",
                input_summary=task_input.encode(),
            )
        ),
    )


def build_vm_media_create_input(
    request: Request,
    item: MediaItem,
    target: MediaCopyTarget,
    form: Mapping[str, object],
) -> VmMediaCreateInput:
    if (
        item.status != MediaStatus.AVAILABLE
        or item.kind not in {MediaKind.QCOW2, MediaKind.RAW}
        or item.sha256 is None
        or json.loads(item.backing_chain_json) != []
        or target.pool.persistent_hash is None
    ):
        raise ValueError("Platform image is unavailable or has an external backing chain")
    network = network_identity(
        request.app.state.database,
        target.host.id,
        str(form.get("network_resource_id", "")),
    )
    iso = iso_identity(
        request.app.state.database,
        target.host.id,
        str(form.get("iso_resource_id", "")),
    )
    driver_iso = iso_identity(
        request.app.state.database,
        target.host.id,
        str(form.get("driver_iso_resource_id", "")),
    )
    cloud_enabled = str(form.get("cloud_init", "")) == "enabled"
    network_mac = _random_mac() if cloud_enabled else None
    password_hash = (
        hash_guest_password(
            str(form.get("cloud_password", "")),
            str(form.get("cloud_password_confirmation", "")),
        )
        if cloud_enabled
        else None
    )
    network_mode = str(form.get("cloud_network_mode", "dhcp"))
    target_capacity = _target_capacity(form.get("target_capacity_gib"))
    create = VmMediaCreateInput(
        media_item_id=item.id,
        media_sha256=item.sha256,
        media_format=item.kind,
        host_id=target.host.id,
        pool_resource_id=target.pool.id,
        pool_uuid=target.pool.native_id,
        pool_generation=target.pool.observed_generation,
        pool_hash=target.pool.persistent_hash,
        target_file_name=str(form.get("target_file_name", "")),
        name=str(form.get("name", "")),
        memory_mib=int(str(form.get("memory_mib", "0"))),
        vcpus=int(str(form.get("vcpus", "0"))),
        vm_uuid=str(uuid4()),
        network_kind=network[0],
        network_resource_id=network[1],
        network_native_id=network[2],
        network_generation=network[3],
        network_hash=network[4],
        network_name=network[5],
        network_mac=network_mac,
        iso_resource_id=iso[0],
        iso_native_id=iso[1],
        iso_generation=iso[2],
        iso_hash=iso[3],
        iso_key=iso[4],
        iso_name=iso[5],
        cloud_hostname=str(form.get("cloud_hostname", "")) if cloud_enabled else None,
        cloud_username=str(form.get("cloud_username", "")) if cloud_enabled else None,
        cloud_ssh_public_key=(
            str(form.get("cloud_ssh_public_key", "")).strip() or None if cloud_enabled else None
        ),
        cloud_password_hash=password_hash,
        cloud_network_mode=network_mode if cloud_enabled else None,
        cloud_ipv4_cidr=(
            str(form.get("cloud_ipv4_cidr", "")).strip() or None
            if cloud_enabled and network_mode == "static"
            else None
        ),
        cloud_ipv4_gateway=(
            str(form.get("cloud_ipv4_gateway", "")).strip() or None
            if cloud_enabled and network_mode == "static"
            else None
        ),
        cloud_ipv6_cidr=(
            str(form.get("cloud_ipv6_cidr", "")).strip() or None
            if cloud_enabled and network_mode == "static"
            else None
        ),
        cloud_ipv6_gateway=(
            str(form.get("cloud_ipv6_gateway", "")).strip() or None
            if cloud_enabled and network_mode == "static"
            else None
        ),
        cloud_dns_addresses=(
            _dns_addresses(form.get("cloud_dns_addresses"))
            if cloud_enabled and network_mode == "static"
            else ()
        ),
        source_virtual_size_bytes=item.virtual_size_bytes,
        target_capacity_bytes=target_capacity,
        disk_bus=str(form.get("disk_bus", "virtio")),
        cpu_mode=str(form.get("cpu_mode", "host-model")),
        guest_profile=str(form.get("guest_profile", "linux")),
        firmware=str(form.get("firmware", "bios")),
        secure_boot=form.get("secure_boot", "") == "on",
        tpm2=form.get("tpm2", "") == "on",
        driver_iso_resource_id=driver_iso[0],
        driver_iso_native_id=driver_iso[1],
        driver_iso_generation=driver_iso[2],
        driver_iso_hash=driver_iso[3],
        driver_iso_key=driver_iso[4],
        driver_iso_name=driver_iso[5],
    )
    create.validate()
    return create


def eligible_media(request: Request) -> list[MediaItem]:
    return [
        item
        for item in request.app.state.media_index_store.list_items()
        if item.status == MediaStatus.AVAILABLE
        and item.kind in {MediaKind.QCOW2, MediaKind.RAW}
        and item.backing_chain_json == "[]"
    ]


def media_target(request: Request, resource_id: str) -> MediaCopyTarget | None:
    return next(
        (
            target
            for target in MediaCopyTargetService(request.app.state.database).list_targets()
            if target.pool.id == resource_id
        ),
        None,
    )


def _random_mac() -> str:
    suffix = secrets.token_bytes(3)
    return "52:54:00:" + ":".join(f"{value:02x}" for value in suffix)


def _dns_addresses(value: object) -> tuple[str, ...]:
    text = str(value or "")
    return tuple(item.strip() for item in text.split(",") if item.strip())


def _target_capacity(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    gib = int(text)
    if not 1 <= gib <= 16 * 1024:
        raise ValueError("target capacity GiB is invalid")
    return gib * 1024**3


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
