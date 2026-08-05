"""JSON APIs for deleting pools and resizing or deleting volumes."""

from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteConflict
from nexora.resources.models import ResourceType
from nexora.storage.read_service import StorageReadService, StorageVolumeView
from nexora.storage.service import StoragePoolError
from nexora.storage.task_contracts import StoragePoolTaskInput
from nexora.storage.volume_contracts import StorageVolumeMutationInput
from nexora.storage.volume_models import StorageVolumeChangePlan
from nexora.storage.volume_service import StorageVolumeError
from nexora.storage.volume_tasks import StorageVolumeTaskInput
from nexora.tasks.definitions import TaskCreate
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import TaskCreatedResponse

router = APIRouter(prefix="/internal", include_in_schema=False)


class StorageMutationPreviewRequest(BaseModel):
    resource_id: str = Field(min_length=1, max_length=64)
    operation: Literal["pool_delete", "volume_resize", "volume_delete"]
    target_capacity_gib: int | None = Field(default=None, ge=1, le=8 * 1024**2)


class StorageMutationApplyRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=64)
    confirmation_token: str = Field(min_length=1, max_length=128)
    host_id: str = Field(min_length=1, max_length=64)
    pool_uuid: str = Field(min_length=1, max_length=128)
    operation: Literal["pool_delete", "volume_resize", "volume_delete"]


@router.post("/storage/mutations/preview")
async def preview_storage_mutation(
    request: Request,
    submitted: StorageMutationPreviewRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    try:
        if submitted.operation == "pool_delete":
            preview = await _preview_pool_delete(request, submitted.resource_id)
            pool_uuid = preview.plan.pool_uuid
            host_id = preview.plan.host_id
            summary = {"name": preview.plan.pool_name}
        else:
            preview = await _preview_volume(request, submitted)
            pool_uuid = preview.plan.pool_uuid
            host_id = preview.plan.host_id
            summary = {"name": preview.plan.volume_name}
    except (
        TypeError,
        ValueError,
        ResourceWriteConflict,
        StoragePoolError,
        StorageVolumeError,
    ) as exc:
        return internal_error(422, "storage_mutation_preview_failed", str(exc))
    return no_store(
        JSONResponse(
            {
                "plan_id": preview.plan.id,
                "confirmation_token": preview.confirmation_token,
                "host_id": host_id,
                "pool_uuid": pool_uuid,
                "operation": submitted.operation,
                "diff_text": preview.plan.diff_text,
                "summary": summary,
            }
        )
    )


@router.post("/storage/mutations/apply")
async def apply_storage_mutation(
    request: Request,
    submitted: StorageMutationApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    service = (
        request.app.state.storage_pool_delete_service
        if submitted.operation == "pool_delete"
        else request.app.state.storage_volume_mutation_service
    )
    try:
        plan = await run_in_threadpool(
            service.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            host_id=submitted.host_id,
            pool_uuid=submitted.pool_uuid,
        )
    except (StoragePoolError, StorageVolumeError) as exc:
        return internal_error(409, "storage_mutation_confirmation_failed", str(exc))
    if submitted.operation == "pool_delete":
        return _enqueue_pool_delete(request, plan)
    return _enqueue_volume_mutation(request, plan)


async def _preview_pool_delete(request: Request, resource_id: str) -> Any:
    pool = StorageReadService(request.app.state.database).pool(resource_id)
    if pool is None or pool.pool.persistent_hash is None:
        raise ValueError("writable storage pool not found")
    base = ResourceBaseVersion(
        pool.pool.id,
        pool.host.id,
        ResourceType.STORAGE_POOL,
        pool.pool.native_id,
        pool.pool.observed_generation,
        pool.pool.persistent_hash,
        None,
    )
    return await run_in_threadpool(request.app.state.storage_pool_delete_service.preview, base)


async def _preview_volume(
    request: Request,
    submitted: StorageMutationPreviewRequest,
) -> Any:
    volume = StorageReadService(request.app.state.database).volume(submitted.resource_id)
    if volume is None:
        raise ValueError("writable storage volume not found")
    operation = "resize" if submitted.operation == "volume_resize" else "delete"
    change = _volume_change(volume, operation, submitted.target_capacity_gib)
    service = request.app.state.storage_volume_mutation_service
    method = service.preview_resize if operation == "resize" else service.preview_delete
    return await run_in_threadpool(method, change)


def _volume_change(
    view: StorageVolumeView,
    operation: str,
    target_capacity_gib: int | None,
) -> StorageVolumeMutationInput:
    pool = view.pool
    volume = view.volume
    details = view.details
    if pool.persistent_hash is None or volume.persistent_hash is None:
        raise ValueError("storage volume version is unavailable")
    target = target_capacity_gib * 1024**3 if target_capacity_gib is not None else None
    change = StorageVolumeMutationInput(
        host_id=view.host.id,
        pool_resource_id=pool.id,
        pool_uuid=pool.native_id,
        pool_generation=pool.observed_generation,
        pool_hash=pool.persistent_hash,
        volume_resource_id=volume.id,
        volume_native_id=volume.native_id,
        volume_generation=volume.observed_generation,
        volume_hash=volume.persistent_hash,
        volume_key=str(details.get("key", "")),
        volume_name=volume.display_name,
        current_capacity_bytes=_integer(details.get("capacity_bytes")),
        target_capacity_bytes=target,
    )
    change.validate(operation)
    return change


def _enqueue_pool_delete(request: Request, plan: Any) -> JSONResponse:
    task_input = StoragePoolTaskInput(plan.id, plan.host_id, plan.pool_uuid, "delete")
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="storage.pool_change",
            title=f"移除存储池定义 · {plan.pool_name}",
            idempotency_scope=f"host:{plan.host_id}:pool:{plan.pool_uuid}:delete",
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


def _enqueue_volume_mutation(
    request: Request,
    plan: StorageVolumeChangePlan,
) -> JSONResponse:
    volume_native_id = str(plan.volume_native_id)
    task_input = StorageVolumeTaskInput(
        plan.id, plan.host_id, plan.pool_uuid, plan.operation, volume_native_id
    )
    title = "扩容" if plan.operation == "resize" else "删除"
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="storage.volume_change",
            title=f"{title}存储卷 · {plan.volume_name}",
            idempotency_scope=f"host:{plan.host_id}:volume:{volume_native_id}",
            idempotency_key=plan.id,
            host_id=plan.host_id,
            resource_type=ResourceType.STORAGE_VOLUME,
            resource_id=volume_native_id,
            total_steps=3,
            resumable=False,
            recovery_strategy="verify_only",
            input_summary=task_input.encode(),
        )
    )
    return _task_response(task.id)


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)


def _task_response(task_id: str) -> JSONResponse:
    payload = TaskCreatedResponse(task_id=task_id, location=f"/tasks/{task_id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=201))


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("storage volume capacity is invalid")
    return value
