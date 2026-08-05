"""Managed-volume VM creation preview, confirmation, and task submission."""

from collections.abc import Mapping
from typing import cast
from uuid import uuid4

from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from nexora.auth.sessions import SessionIdentity, SessionService
from nexora.db import Database
from nexora.resources.models import ResourceType
from nexora.storage.read_service import StorageReadService, StorageVolumeView
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.models import Task
from nexora.vms.creation_authority import VmCreationConflict
from nexora.vms.creation_contracts import VmImportCreateInput
from nexora.vms.creation_models import VmCreationPlan
from nexora.vms.creation_service import VmCreationError, VmCreationService
from nexora.vms.creation_tasks import VmCreationTaskInput
from nexora.web.rendering import templates
from nexora.web.routes.vm_create_options import (
    eligible_isos,
    eligible_networks,
    eligible_volumes,
    iso_identity,
    network_identity,
)
from nexora.web.security import CSRF_COOKIE, SESSION_COOKIE

router = APIRouter(include_in_schema=False)


@router.get("/vms/create")
async def vm_create_form(request: Request) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="vms/create.html",
        context={
            "administrator": identity,
            "csrf_token": _csrf(request),
            "volumes": eligible_volumes(request.app.state.database),
            "networks": eligible_networks(request.app.state.database),
            "isos": eligible_isos(request.app.state.database),
            "form_values": {},
        },
    )


@router.post("/vms/create/preview")
async def vm_create_preview(request: Request) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    volume = StorageReadService(request.app.state.database).volume(
        str(form.get("volume_resource_id", ""))
    )
    if volume is None:
        return PlainTextResponse("Managed storage volume not found", status_code=404)
    try:
        create = build_vm_create_input(request.app.state.database, volume, form)
        service: VmCreationService = request.app.state.vm_creation_service
        preview = await run_in_threadpool(service.preview, create)
    except (TypeError, ValueError, RuntimeError, VmCreationError, VmCreationConflict) as exc:
        return templates.TemplateResponse(
            request=request,
            name="vms/create.html",
            context={
                "administrator": identity,
                "csrf_token": _csrf(request),
                "volumes": eligible_volumes(request.app.state.database),
                "networks": eligible_networks(request.app.state.database),
                "isos": eligible_isos(request.app.state.database),
                "error": str(exc),
                "form_values": {
                    "name": str(form.get("name", "")),
                    "memory_mib": str(form.get("memory_mib", "2048")),
                    "vcpus": str(form.get("vcpus", "2")),
                    "disk_bus": str(form.get("disk_bus", "virtio")),
                    "cpu_mode": str(form.get("cpu_mode", "host-model")),
                    "guest_profile": str(form.get("guest_profile", "linux")),
                    "firmware": str(form.get("firmware", "bios")),
                },
            },
            status_code=422,
        )
    return templates.TemplateResponse(
        request=request,
        name="vms/create_preview.html",
        context={
            "administrator": identity,
            "csrf_token": _csrf(request),
            "preview": preview,
            "create": create,
            "volume": volume,
        },
    )


@router.post("/vms/create/apply")
async def vm_create_apply(request: Request) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    service: VmCreationService = request.app.state.vm_creation_service
    try:
        plan = await run_in_threadpool(
            service.confirm,
            str(form.get("plan_id", "")),
            str(form.get("confirmation_token", "")),
            host_id=str(form.get("host_id", "")),
            vm_uuid=str(form.get("vm_uuid", "")),
        )
    except (VmCreationError, VmCreationConflict) as exc:
        return PlainTextResponse(str(exc), status_code=409)
    task = enqueue_vm_creation(request, plan)
    return RedirectResponse(f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


def enqueue_vm_creation(request: Request, plan: VmCreationPlan) -> Task:
    task_input = VmCreationTaskInput(plan.id, plan.host_id, plan.vm_uuid)
    return cast(
        Task,
        request.app.state.task_queue.enqueue(
            TaskCreate(
                task_type="vm.create",
                title=f"创建虚拟机 · {plan.vm_name}",
                idempotency_scope=f"host:{plan.host_id}:vm:{plan.vm_uuid}:create",
                idempotency_key=plan.id,
                host_id=plan.host_id,
                vm_uuid=plan.vm_uuid,
                resource_type=ResourceType.VIRTUAL_MACHINE,
                resource_id=plan.vm_uuid,
                total_steps=3,
                resumable=False,
                recovery_strategy="verify_only",
                input_summary=task_input.encode(),
            )
        ),
    )


def build_vm_create_input(
    database: Database,
    volume: StorageVolumeView,
    form: Mapping[str, object],
) -> VmImportCreateInput:
    pool_hash = volume.pool.persistent_hash
    volume_hash = volume.volume.persistent_hash
    volume_key = volume.details.get("key")
    capacity = volume.details.get("capacity_bytes")
    if (
        pool_hash is None
        or volume_hash is None
        or not isinstance(volume_key, str)
        or not isinstance(capacity, int)
        or isinstance(capacity, bool)
    ):
        raise ValueError("Managed storage volume metadata is incomplete")
    network = network_identity(
        database,
        volume.host.id,
        str(form.get("network_resource_id", "")),
    )
    iso = iso_identity(
        database,
        volume.host.id,
        str(form.get("iso_resource_id", "")),
    )
    driver_iso = iso_identity(
        database,
        volume.host.id,
        str(form.get("driver_iso_resource_id", "")),
    )
    create = VmImportCreateInput(
        host_id=volume.host.id,
        pool_resource_id=volume.pool.id,
        pool_uuid=volume.pool.native_id,
        pool_generation=volume.pool.observed_generation,
        pool_hash=pool_hash,
        volume_resource_id=volume.volume.id,
        volume_native_id=volume.volume.native_id,
        volume_generation=volume.volume.observed_generation,
        volume_hash=volume_hash,
        volume_key=volume_key,
        volume_name=volume.volume.display_name,
        current_capacity_bytes=capacity,
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
        iso_resource_id=iso[0],
        iso_native_id=iso[1],
        iso_generation=iso[2],
        iso_hash=iso[3],
        iso_key=iso[4],
        iso_name=iso[5],
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
