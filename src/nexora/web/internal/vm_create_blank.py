"""Session-only JSON API for blank-disk VM creation."""

from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from nexora.db import Database
from nexora.resources.models import ResourceType
from nexora.storage.read_service import StoragePoolView, StorageReadService
from nexora.tasks.definitions import TaskCreate
from nexora.vms.blank_creation_authority import VmBlankCreationConflict
from nexora.vms.blank_creation_contracts import VmBlankCreateInput
from nexora.vms.blank_creation_service import VmBlankCreationError, VmBlankCreationService
from nexora.vms.blank_creation_tasks import VmBlankCreationTaskInput
from nexora.web.internal.auth import (
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import (
    InternalError,
    TaskCreatedResponse,
    VmBlankCreateOptionsResponse,
    VmBlankCreatePoolOption,
    VmBlankCreatePreviewRequest,
    VmBlankCreatePreviewResponse,
    VmBlankCreatePreviewSummary,
    VmCreateApplyRequest,
    VmCreateIsoOption,
    VmCreateNetworkOption,
)
from nexora.web.routes.vm_create_options import eligible_isos, eligible_networks

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.get("/vm-create/blank-disk/options")
async def vm_blank_create_options(request: Request) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    database = request.app.state.database
    payload = VmBlankCreateOptionsResponse(
        pools=[
            VmBlankCreatePoolOption(
                id=item.pool.id,
                host_id=item.host.id,
                host_name=item.host.name,
                pool_name=item.pool.display_name,
                target_path=str(item.details.get("target_path", "")),
            )
            for item in _writable_pools(database)
        ],
        networks=[
            VmCreateNetworkOption(
                id=item.resource.id,
                host_id=item.host.id,
                host_name=item.host.name,
                kind=item.kind,
                name=item.resource.display_name,
            )
            for item in eligible_networks(database)
        ],
        isos=[
            VmCreateIsoOption(
                id=item.volume.id,
                host_id=item.host.id,
                host_name=item.host.name,
                pool_name=item.pool.display_name,
                name=item.volume.display_name,
            )
            for item in eligible_isos(database)
        ],
    )
    return no_store(JSONResponse(payload.model_dump()))


@router.post("/vm-create/blank-disk/preview")
async def vm_blank_create_preview(
    request: Request,
    submitted: VmBlankCreatePreviewRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    pool = StorageReadService(request.app.state.database).pool(submitted.pool_resource_id)
    if pool is None:
        return _error(404, "storage_pool_not_found", "可写存储池不存在")
    if pool.pool.persistent_hash is None:
        return _error(409, "storage_pool_not_writable", "存储池不可写")
    values = submitted.model_dump()
    values.update(
        secure_boot="on" if submitted.secure_boot else "",
        tpm2="on" if submitted.tpm2 else "",
        capacity_bytes=submitted.capacity_gib * 1024**3,
    )
    try:
        create = build_blank_create_input(request, pool, values)
        service: VmBlankCreationService = request.app.state.vm_blank_creation_service
        preview = await run_in_threadpool(service.preview, create)
    except (TypeError, ValueError, RuntimeError, VmBlankCreationError) as exc:
        return _error(422, "vm_blank_preview_failed", str(exc))
    payload = VmBlankCreatePreviewResponse(
        plan_id=preview.plan.id,
        confirmation_token=preview.confirmation_token,
        host_id=create.host_id,
        vm_uuid=create.vm_uuid,
        diff_text=preview.plan.diff_text,
        summary=VmBlankCreatePreviewSummary(
            name=create.name,
            host_name=pool.host.name,
            vcpus=create.vcpus,
            memory_mib=create.memory_mib,
            pool_name=pool.pool.display_name,
            disk_name=create.disk_name,
            volume_format=create.volume_format,
            capacity_bytes=create.capacity_bytes,
            network=(
                "无网卡"
                if create.network_kind == "none"
                else f"{create.network_kind} / {create.network_name}"
            ),
            iso_name=create.iso_name,
            firmware=create.firmware,
            secure_boot=create.secure_boot,
            tpm2=create.tpm2,
        ),
    )
    return no_store(JSONResponse(payload.model_dump()))


@router.post("/vm-create/blank-disk/apply")
async def vm_blank_create_apply(
    request: Request,
    submitted: VmCreateApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    service: VmBlankCreationService = request.app.state.vm_blank_creation_service
    try:
        plan = await run_in_threadpool(
            service.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            host_id=submitted.host_id,
            vm_uuid=submitted.vm_uuid,
        )
    except (VmBlankCreationError, VmBlankCreationConflict) as exc:
        return _error(409, "vm_blank_confirmation_failed", str(exc))
    task_input = VmBlankCreationTaskInput(plan.id, plan.host_id, plan.vm_uuid)
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.create_blank",
            title=f"创建虚拟机 · {plan.vm_name}",
            idempotency_scope=f"host:{plan.host_id}:vm:{plan.vm_uuid}:create_blank",
            idempotency_key=plan.id,
            host_id=plan.host_id,
            vm_uuid=plan.vm_uuid,
            resource_type=ResourceType.VIRTUAL_MACHINE,
            resource_id=plan.vm_uuid,
            total_steps=3,
            resumable=True,
            max_retries=2,
            recovery_strategy="resume_from_checkpoint",
            input_summary=task_input.encode(),
        )
    )
    response = TaskCreatedResponse(task_id=task.id, location=f"/tasks/{task.id}")
    return no_store(JSONResponse(response.model_dump(), status_code=201))


def build_blank_create_input(
    request: Request,
    pool: StoragePoolView,
    values: dict[str, object],
) -> VmBlankCreateInput:
    from nexora.web.routes.vm_create_options import iso_identity, network_identity

    database = request.app.state.database
    network = network_identity(database, pool.host.id, str(values.get("network_resource_id", "")))
    iso = iso_identity(database, pool.host.id, str(values.get("iso_resource_id", "")))
    driver_iso = iso_identity(database, pool.host.id, str(values.get("driver_iso_resource_id", "")))
    create = VmBlankCreateInput(
        host_id=pool.host.id,
        pool_resource_id=pool.pool.id,
        pool_uuid=pool.pool.native_id,
        pool_generation=pool.pool.observed_generation,
        pool_hash=str(pool.pool.persistent_hash),
        disk_name=str(values.get("disk_name", "")),
        volume_format=str(values.get("volume_format", "qcow2")),
        capacity_bytes=_strict_int(values.get("capacity_bytes", 0)),
        name=str(values.get("name", "")),
        memory_mib=_strict_int(values.get("memory_mib", 0)),
        vcpus=_strict_int(values.get("vcpus", 0)),
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
        disk_bus=str(values.get("disk_bus", "virtio")),
        cpu_mode=str(values.get("cpu_mode", "host-model")),
        guest_profile=str(values.get("guest_profile", "linux")),
        firmware=str(values.get("firmware", "bios")),
        secure_boot=values.get("secure_boot", "") == "on",
        tpm2=values.get("tpm2", "") == "on",
        driver_iso_resource_id=driver_iso[0],
        driver_iso_native_id=driver_iso[1],
        driver_iso_generation=driver_iso[2],
        driver_iso_hash=driver_iso[3],
        driver_iso_key=driver_iso[4],
        driver_iso_name=driver_iso[5],
    )
    create.validate()
    return create


def _writable_pools(database: Database) -> list[StoragePoolView]:
    return [
        item
        for item in StorageReadService(database).pools()
        if item.pool.status == "managed"
        and item.details.get("pool_type") in {"dir", "netfs"}
        and bool(item.details.get("active"))
        and item.pool.persistent_hash is not None
    ]


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)


def _strict_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("value must be an integer")
    return value


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    payload = InternalError(code=code, message=message)
    return no_store(JSONResponse(payload.model_dump(), status_code=status_code))
