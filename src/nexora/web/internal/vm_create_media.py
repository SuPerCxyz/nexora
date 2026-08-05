"""Session-only API for platform-image VM creation."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from nexora.media.copy_read import MediaCopyTargetService
from nexora.vms.media_creation_authority import VmMediaCreationConflict
from nexora.vms.media_creation_service import VmMediaCreationError, VmMediaCreationService
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
    VmMediaCreateOptionsResponse,
    VmMediaCreatePreviewRequest,
    VmMediaCreatePreviewResponse,
    VmMediaCreatePreviewSummary,
    VmMediaOption,
    VmMediaTargetOption,
)
from nexora.web.routes.vm_create_media import (
    build_vm_media_create_input,
    eligible_media,
    enqueue_vm_media_creation,
    media_target,
)
from nexora.web.routes.vm_create_options import eligible_isos, eligible_networks

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.get("/vm-create/platform-image/options")
async def vm_media_create_options(request: Request) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    database = request.app.state.database
    payload = VmMediaCreateOptionsResponse(
        media=[
            VmMediaOption(
                id=item.id,
                file_name=item.file_name,
                format=item.kind,
                size_bytes=item.size_bytes,
                virtual_size_bytes=item.virtual_size_bytes,
            )
            for item in eligible_media(request)
        ],
        targets=[
            VmMediaTargetOption(
                id=item.pool.id,
                host_id=item.host.id,
                host_name=item.host.name,
                pool_name=item.pool.display_name,
                target_path=item.target_path,
            )
            for item in MediaCopyTargetService(database).list_targets()
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


@router.post("/vm-create/platform-image/preview")
async def vm_media_create_preview(
    request: Request,
    submitted: VmMediaCreatePreviewRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    item = request.app.state.media_index_store.get_item(submitted.media_item_id)
    target = media_target(request, submitted.pool_resource_id)
    if item is None or target is None:
        return _error(404, "media_or_target_not_found", "平台镜像或目标 Pool 不存在")
    values = submitted.model_dump()
    values.update(
        cloud_init="enabled" if submitted.cloud_init else "",
        secure_boot="on" if submitted.secure_boot else "",
        tpm2="on" if submitted.tpm2 else "",
        cloud_dns_addresses=",".join(submitted.cloud_dns_addresses),
        target_capacity_gib=submitted.target_capacity_gib or "",
    )
    try:
        create = await run_in_threadpool(
            build_vm_media_create_input,
            request,
            item,
            target,
            values,
        )
        service: VmMediaCreationService = request.app.state.vm_media_creation_service
        preview = await run_in_threadpool(service.preview, create)
    except (TypeError, ValueError, RuntimeError, VmMediaCreationError) as exc:
        return _error(422, "vm_media_preview_failed", str(exc))
    payload = VmMediaCreatePreviewResponse(
        plan_id=preview.plan.id,
        confirmation_token=preview.confirmation_token,
        host_id=create.host_id,
        vm_uuid=create.vm_uuid,
        diff_text=preview.plan.diff_text,
        summary=VmMediaCreatePreviewSummary(
            name=create.name,
            host_name=target.host.name,
            media_name=item.file_name,
            pool_name=target.pool.display_name,
            target_path=preview.target_path,
            source_sha256=item.sha256,
            vcpus=create.vcpus,
            memory_mib=create.memory_mib,
            target_capacity_bytes=create.target_capacity_bytes,
            network=(
                "无网卡"
                if create.network_kind == "none"
                else f"{create.network_kind} / {create.network_name}"
            ),
            iso_name=create.iso_name,
            driver_iso_name=create.driver_iso_name,
            firmware=create.firmware,
            secure_boot=create.secure_boot,
            tpm2=create.tpm2,
            cloud_init=(
                f"{create.cloud_username}@{create.cloud_hostname} · {create.cloud_network_mode}"
                if create.cloud_username
                else None
            ),
        ),
    )
    return no_store(JSONResponse(payload.model_dump()))


@router.post("/vm-create/platform-image/apply")
async def vm_media_create_apply(
    request: Request,
    submitted: VmCreateApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    service: VmMediaCreationService = request.app.state.vm_media_creation_service
    try:
        plan = await run_in_threadpool(
            service.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            host_id=submitted.host_id,
            vm_uuid=submitted.vm_uuid,
        )
    except (VmMediaCreationError, VmMediaCreationConflict) as exc:
        return _error(409, "vm_media_confirmation_failed", str(exc))
    task = enqueue_vm_media_creation(request, plan)
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
