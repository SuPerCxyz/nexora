"""Session-only storage reads and create operations."""

from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceType
from nexora.storage.contracts import StoragePoolCreateInput, parse_mount_options
from nexora.storage.read_service import StoragePoolView, StorageReadService, StorageVolumeView
from nexora.storage.service import StoragePoolError, StoragePoolService
from nexora.storage.task_contracts import (
    StoragePoolAction,
    StoragePoolLifecycleInput,
    StoragePoolTaskInput,
)
from nexora.storage.usage import StoragePoolUsageGuard
from nexora.storage.volume_contracts import StorageVolumeCreateInput, is_display_volume
from nexora.storage.volume_service import StorageVolumeError, StorageVolumeService
from nexora.storage.volume_tasks import StorageVolumeTaskInput
from nexora.tasks.definitions import TaskCreate
from nexora.web.internal.auth import (
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import InternalError, TaskCreatedResponse
from nexora.web.internal.storage_contracts import (
    StorageChangeApplyRequest,
    StorageChangePreviewResponse,
    StorageHostOption,
    StorageOverviewResponse,
    StoragePoolCreateRequest,
    StoragePoolLifecycleRequest,
    StoragePoolPreviewSummary,
    StoragePoolSummary,
    StorageVolumeCreateRequest,
    StorageVolumePreviewSummary,
    StorageVolumeSummary,
)

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.get("/storage")
async def storage_overview(request: Request) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    reads = StorageReadService(request.app.state.database)
    volumes = [
        view
        for view in reads.volumes()
        if is_display_volume(view.volume.display_name, str(view.details.get("format") or ""))
    ]
    usage = StoragePoolUsageGuard(request.app.state.database)
    payload = StorageOverviewResponse(
        hosts=[StorageHostOption(id=item.id, name=item.name) for item in reads.hosts()],
        pools=[_pool_summary(item) for item in reads.pools()],
        volumes=[_volume_summary(view, usage) for view in volumes],
    )
    return _response(payload.model_dump())


@router.post("/storage/pools/preview")
async def storage_pool_preview(
    request: Request,
    submitted: StoragePoolCreateRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    try:
        create = StoragePoolCreateInput(
            host_id=submitted.host_id,
            name=submitted.name,
            pool_type=submitted.pool_type,
            target_path=submitted.target_path,
            source_host=submitted.source_host if submitted.pool_type == "netfs" else None,
            source_path=submitted.source_path if submitted.pool_type == "netfs" else None,
            nfs_version=submitted.nfs_version if submitted.pool_type == "netfs" else None,
            mount_options=(
                parse_mount_options(",".join(submitted.mount_options))
                if submitted.pool_type == "netfs"
                else ()
            ),
            start=submitted.start,
            autostart=submitted.autostart,
        )
        service: StoragePoolService = request.app.state.storage_pool_service
        preview = await run_in_threadpool(service.preview_create, create)
    except (ValueError, RuntimeError, StoragePoolError) as exc:
        return _error(422, "storage_pool_preview_failed", str(exc))
    summary = StoragePoolPreviewSummary(
        name=create.name,
        pool_type=create.pool_type,
        target_path=create.target_path,
        pool_uuid=preview.plan.pool_uuid,
        start=create.start,
        autostart=create.autostart,
    )
    payload = StorageChangePreviewResponse(
        plan_id=preview.plan.id,
        confirmation_token=preview.confirmation_token,
        host_id=preview.plan.host_id,
        pool_uuid=preview.plan.pool_uuid,
        diff_text=preview.plan.diff_text,
        operation="pool_create",
        summary=summary.model_dump(),
    )
    return _response(payload.model_dump())


@router.post("/storage/pools/apply")
async def storage_pool_apply(
    request: Request,
    submitted: StorageChangeApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    service: StoragePoolService = request.app.state.storage_pool_service
    try:
        plan = await run_in_threadpool(
            service.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            host_id=submitted.host_id,
            pool_uuid=submitted.pool_uuid,
        )
    except StoragePoolError as exc:
        return _error(409, "storage_pool_confirmation_failed", str(exc))
    task_input = StoragePoolTaskInput(plan.id, plan.host_id, plan.pool_uuid, "create")
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="storage.pool_change",
            title=f"创建存储池 · {plan.pool_name}",
            idempotency_scope=f"host:{plan.host_id}:pool:{plan.pool_uuid}",
            idempotency_key=plan.id,
            host_id=plan.host_id,
            resource_type=ResourceType.STORAGE_POOL,
            resource_id=plan.pool_uuid,
            total_steps=4,
            resumable=True,
            max_retries=2,
            recovery_strategy="retry_from_start",
            input_summary=task_input.encode(),
        )
    )
    return _task_response(task.id)


@router.post("/storage/volumes/preview")
async def storage_volume_preview(
    request: Request,
    submitted: StorageVolumeCreateRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    pool = StorageReadService(request.app.state.database).pool(submitted.pool_resource_id)
    if pool is None or pool.pool.persistent_hash is None:
        return _error(404, "storage_pool_not_found", "可写存储池不存在")
    try:
        create = StorageVolumeCreateInput(
            host_id=pool.host.id,
            pool_resource_id=pool.pool.id,
            pool_uuid=pool.pool.native_id,
            pool_generation=pool.pool.observed_generation,
            pool_hash=pool.pool.persistent_hash,
            name=submitted.name,
            volume_format=submitted.volume_format,
            capacity_bytes=submitted.capacity_gib * 1024**3,
        )
        service: StorageVolumeService = request.app.state.storage_volume_service
        preview = await run_in_threadpool(service.preview_create, create)
    except (TypeError, ValueError, RuntimeError, StorageVolumeError) as exc:
        return _error(422, "storage_volume_preview_failed", str(exc))
    summary = StorageVolumePreviewSummary(
        name=create.name,
        pool_name=pool.pool.display_name,
        volume_format=create.volume_format,
        capacity_bytes=create.capacity_bytes,
    )
    payload = StorageChangePreviewResponse(
        plan_id=preview.plan.id,
        confirmation_token=preview.confirmation_token,
        host_id=preview.plan.host_id,
        pool_uuid=preview.plan.pool_uuid,
        diff_text=preview.plan.diff_text,
        operation="volume_create",
        summary=summary.model_dump(),
    )
    return _response(payload.model_dump())


@router.post("/storage/volumes/apply")
async def storage_volume_apply(
    request: Request,
    submitted: StorageChangeApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    service: StorageVolumeService = request.app.state.storage_volume_service
    try:
        plan = await run_in_threadpool(
            service.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            host_id=submitted.host_id,
            pool_uuid=submitted.pool_uuid,
        )
    except StorageVolumeError as exc:
        return _error(409, "storage_volume_confirmation_failed", str(exc))
    task_input = StorageVolumeTaskInput(plan.id, plan.host_id, plan.pool_uuid, "create")
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="storage.volume_change",
            title=f"创建存储卷 · {plan.volume_name}",
            idempotency_scope=f"host:{plan.host_id}:pool:{plan.pool_uuid}:volume",
            idempotency_key=plan.id,
            host_id=plan.host_id,
            resource_type=ResourceType.STORAGE_VOLUME,
            resource_id=plan.pool_uuid,
            total_steps=3,
            resumable=True,
            max_retries=2,
            recovery_strategy="retry_from_start",
            input_summary=task_input.encode(),
        )
    )
    return _task_response(task.id)


@router.post("/storage/pools/lifecycle")
async def storage_pool_lifecycle(
    request: Request,
    submitted: StoragePoolLifecycleRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    pool = StorageReadService(request.app.state.database).pool(submitted.resource_id)
    if pool is None or pool.pool.persistent_hash is None:
        return _error(404, "storage_pool_not_found", "可写存储池不存在")
    try:
        action = StoragePoolAction(submitted.action)
        base = ResourceBaseVersion(
            resource_id=pool.pool.id,
            host_id=pool.host.id,
            resource_type=ResourceType.STORAGE_POOL,
            native_id=pool.pool.native_id,
            generation=pool.pool.observed_generation,
            persistent_hash=pool.pool.persistent_hash,
            live_hash=None,
        )
        task_input = StoragePoolLifecycleInput.decode(
            StoragePoolLifecycleInput(action, base).encode()
        )
    except (TypeError, ValueError) as exc:
        return _error(422, "storage_pool_lifecycle_failed", str(exc))
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="storage.pool_lifecycle",
            title=f"{_action_title(action)}存储池 · {pool.pool.display_name}",
            idempotency_scope=f"host:{base.host_id}:pool:{base.native_id}:lifecycle",
            idempotency_key=str(uuid4()),
            host_id=base.host_id,
            resource_type=ResourceType.STORAGE_POOL,
            resource_id=base.native_id,
            total_steps=3,
            resumable=False,
            recovery_strategy="verify_only",
            input_summary=task_input.encode(),
        )
    )
    return _task_response(task.id)


def _pool_summary(view: StoragePoolView) -> StoragePoolSummary:
    host = view.host
    pool = view.pool
    details = view.details
    pool_type = str(details.get("pool_type", "unknown"))
    return StoragePoolSummary(
        resource_id=pool.id,
        host_id=host.id,
        host_name=host.name,
        native_id=pool.native_id,
        name=pool.display_name,
        status=str(pool.status),
        pool_type=pool_type,
        state=str(details.get("state", "unknown")),
        active=bool(details.get("active")),
        autostart=bool(details.get("autostart")),
        target_path=_text(details.get("target_path")),
        capacity_bytes=_integer(details.get("capacity_bytes")),
        available_bytes=_integer(details.get("available_bytes")),
        writable=pool.status == "managed" and pool_type in {"dir", "netfs"},
    )


def _volume_summary(view: StorageVolumeView, usage: StoragePoolUsageGuard) -> StorageVolumeSummary:
    details = view.details
    references = usage.volume_references(
        view.host.id,
        pool_name=view.pool.display_name,
        volume_name=view.volume.display_name,
        volume_key=str(view.volume.native_id),
        volume_path=_text(details.get("path")),
    )
    return StorageVolumeSummary(
        resource_id=view.volume.id,
        host_id=view.host.id,
        host_name=view.host.name,
        pool_resource_id=view.pool.id,
        pool_name=view.pool.display_name,
        name=view.volume.display_name,
        status=str(view.volume.status),
        format=_text(details.get("format")),
        capacity_bytes=_integer(details.get("capacity_bytes")),
        allocation_bytes=_integer(details.get("allocation_bytes")),
        in_use=bool(references),
        writable=view.volume.status == "managed" and view.volume.persistent_hash is not None,
    )


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)


def _response(payload: dict[str, object]) -> JSONResponse:
    return no_store(JSONResponse(payload))


def _task_response(task_id: str) -> JSONResponse:
    payload = TaskCreatedResponse(task_id=task_id, location=f"/tasks/{task_id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=201))


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    payload = InternalError(code=code, message=message)
    return no_store(JSONResponse(payload.model_dump(), status_code=status_code))


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _action_title(action: StoragePoolAction) -> str:
    return {
        StoragePoolAction.START: "启动",
        StoragePoolAction.STOP: "停止",
        StoragePoolAction.REFRESH: "刷新",
        StoragePoolAction.AUTOSTART_ENABLE: "启用自动启动",
        StoragePoolAction.AUTOSTART_DISABLE: "禁用自动启动",
    }[action]
