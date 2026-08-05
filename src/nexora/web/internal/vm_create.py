"""Read-only options for the React VM creation form."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from nexora.storage.read_service import StorageReadService
from nexora.vms.creation_authority import VmCreationConflict
from nexora.vms.creation_service import VmCreationError, VmCreationService
from nexora.web.internal.auth import (
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import (
    InternalError,
    TaskCreatedResponse,
    VmCreateApplyRequest,
    VmCreateIsoOption,
    VmCreateNetworkOption,
    VmCreateOptionsResponse,
    VmCreatePreviewRequest,
    VmCreatePreviewResponse,
    VmCreatePreviewSummary,
    VmCreateVolumeOption,
)
from nexora.web.routes.vm_create import build_vm_create_input, enqueue_vm_creation
from nexora.web.routes.vm_create_options import eligible_isos, eligible_networks, eligible_volumes

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.get("/vm-create/options")
async def internal_vm_create_options(request: Request) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    database = request.app.state.database
    payload = VmCreateOptionsResponse(
        volumes=[
            VmCreateVolumeOption(
                id=item.volume.id,
                host_id=item.host.id,
                host_name=item.host.name,
                pool_name=item.pool.display_name,
                name=item.volume.display_name,
                format=str(item.details["format"]),
                capacity_bytes=_capacity(item.details.get("capacity_bytes")),
            )
            for item in eligible_volumes(database)
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


@router.post("/vm-create/preview")
async def internal_vm_create_preview(
    request: Request,
    submitted: VmCreatePreviewRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    volume = StorageReadService(request.app.state.database).volume(submitted.volume_resource_id)
    if volume is None:
        return _error(404, "volume_not_found", "Managed storage volume not found")
    values = submitted.model_dump()
    values["secure_boot"] = "on" if submitted.secure_boot else ""
    values["tpm2"] = "on" if submitted.tpm2 else ""
    try:
        create = build_vm_create_input(request.app.state.database, volume, values)
        service: VmCreationService = request.app.state.vm_creation_service
        preview = await run_in_threadpool(service.preview, create)
    except (TypeError, ValueError, RuntimeError, VmCreationError, VmCreationConflict) as exc:
        return _error(422, "vm_create_preview_failed", str(exc))
    payload = VmCreatePreviewResponse(
        plan_id=preview.plan.id,
        confirmation_token=preview.confirmation_token,
        host_id=create.host_id,
        vm_uuid=create.vm_uuid,
        diff_text=preview.plan.diff_text,
        summary=VmCreatePreviewSummary(
            name=create.name,
            host_name=volume.host.name,
            vcpus=create.vcpus,
            memory_mib=create.memory_mib,
            volume_name=volume.volume.display_name,
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


@router.post("/vm-create/apply")
async def internal_vm_create_apply(
    request: Request,
    submitted: VmCreateApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    service: VmCreationService = request.app.state.vm_creation_service
    try:
        plan = await run_in_threadpool(
            service.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            host_id=submitted.host_id,
            vm_uuid=submitted.vm_uuid,
        )
    except (VmCreationError, VmCreationConflict) as exc:
        return _error(409, "vm_create_confirmation_failed", str(exc))
    task = enqueue_vm_creation(request, plan)
    payload = TaskCreatedResponse(task_id=task.id, location=f"/tasks/{task.id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=201))


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    payload = InternalError(code=code, message=message)
    return no_store(JSONResponse(payload.model_dump(), status_code=status_code))


def _capacity(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("Managed storage volume capacity is invalid")
    return value
