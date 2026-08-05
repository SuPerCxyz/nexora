"""Session-only platform media library APIs."""

from typing import cast
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexora.media.copy_contracts import MediaCopyInput
from nexora.media.copy_read import MediaCopyTarget, MediaCopyTargetService
from nexora.media.credentials import MediaCredentialError
from nexora.media.models import MediaItem, MediaKind, MediaStatus
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.models import Task
from nexora.tasks.read_service import TaskReadService
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import TaskCreatedResponse

router = APIRouter(prefix="/internal", include_in_schema=False)


class MediaCopyRequest(BaseModel):
    pool_resource_id: str = Field(min_length=1, max_length=256)
    target_file_name: str = Field(min_length=1, max_length=255)


@router.get("/media")
async def internal_media(request: Request) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    items = request.app.state.media_index_store.list_items()
    active = TaskReadService(request.app.state.database).find_active("media.scan")
    payload = {
        "items": [
            {
                "id": item.id,
                "relative_path": item.relative_path,
                "file_name": item.file_name,
                "kind": str(item.kind),
                "status": str(item.status),
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
                "image_format": item.image_format,
                "classification": item.classification,
                "architecture": item.architecture,
                "standalone": item.backing_chain_json == "[]",
            }
            for item in items
        ],
        "active_task_id": active.id if active is not None else None,
    }
    return no_store(JSONResponse(payload))


@router.post("/media/scan")
async def internal_media_scan(request: Request) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    csrf_error = verify_internal_csrf(request)
    if csrf_error is not None:
        return csrf_error
    active = TaskReadService(request.app.state.database).find_active("media.scan")
    if active is not None:
        return _task_response(active.id, 200)
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="media.scan",
            title="扫描平台媒体库",
            idempotency_scope="platform:media:scan",
            idempotency_key=str(uuid4()),
            resource_type="media_library",
            resource_id="library",
            total_steps=3,
            resumable=True,
            recovery_strategy="retry_from_start",
        )
    )
    return _task_response(task.id, 201)


@router.post("/media/{media_item_id}/credentials")
async def internal_media_credential_issue(request: Request, media_item_id: str) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    try:
        issued = request.app.state.media_credential_service.issue(media_item_id)
    except (MediaCredentialError, ValueError) as exc:
        return internal_error(422, "media_credential_failed", str(exc))
    content_url = request.url_for("media_content", credential_id=issued.credential.id)
    payload = {
        "credential_id": issued.credential.id,
        "content_url": str(content_url),
        "token": issued.token,
        "expires_at": issued.credential.expires_at.isoformat(),
    }
    return no_store(JSONResponse(payload, status_code=201))


@router.post("/media/credentials/{credential_id}/revoke")
async def internal_media_credential_revoke(request: Request, credential_id: str) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    revoked = request.app.state.media_credential_service.revoke(credential_id)
    if not revoked:
        return internal_error(404, "media_credential_not_found", "访问凭据不存在")
    return no_store(JSONResponse({"revoked": True}))


@router.get("/media/{media_item_id}/copy")
async def internal_media_copy_options(request: Request, media_item_id: str) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    item = request.app.state.media_index_store.get_item(media_item_id)
    if not _copyable(item):
        return internal_error(404, "media_image_not_found", "平台镜像不存在")
    targets = MediaCopyTargetService(request.app.state.database).list_targets()
    payload = {
        "item": {"id": item.id, "file_name": item.file_name, "sha256": item.sha256},
        "targets": [
            {
                "pool_resource_id": target.pool.id,
                "host_name": target.host.name,
                "pool_name": target.pool.display_name,
                "target_path": target.target_path,
            }
            for target in targets
        ],
    }
    return no_store(JSONResponse(payload))


@router.post("/media/{media_item_id}/copy")
async def internal_media_copy(
    request: Request,
    media_item_id: str,
    submitted: MediaCopyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    item = request.app.state.media_index_store.get_item(media_item_id)
    targets = MediaCopyTargetService(request.app.state.database).list_targets()
    target = next(
        (value for value in targets if value.pool.id == submitted.pool_resource_id),
        None,
    )
    if not _copyable(item) or target is None:
        return internal_error(422, "media_copy_invalid", "镜像复制请求无效")
    try:
        copy_input = MediaCopyInput(
            item.id,
            item.sha256,
            target.host.id,
            target.pool.id,
            target.pool.native_id,
            target.pool.observed_generation,
            target.pool.persistent_hash or "",
            submitted.target_file_name,
        )
        copy_input.validate()
    except ValueError as exc:
        return internal_error(422, "media_copy_invalid", str(exc))
    active = TaskReadService(request.app.state.database).find_active(
        "media.image_copy", host_id=target.host.id
    )
    if active is not None:
        return _task_response(active.id, 200)
    task = _enqueue_copy(request, item.file_name, copy_input, target)
    return _task_response(task.id, 201)


def _task_response(task_id: str, status_code: int) -> JSONResponse:
    payload = TaskCreatedResponse(task_id=task_id, location=f"/tasks/{task_id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=status_code))


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)


def _copyable(item: MediaItem | None) -> bool:
    return bool(
        item is not None
        and item.kind in {MediaKind.QCOW2, MediaKind.RAW}
        and item.status == MediaStatus.AVAILABLE
        and item.sha256
    )


def _enqueue_copy(
    request: Request,
    file_name: str,
    copy_input: MediaCopyInput,
    target: MediaCopyTarget,
) -> Task:
    return cast(
        Task,
        request.app.state.task_queue.enqueue(
            TaskCreate(
                task_type="media.image_copy",
                title=f"复制镜像 {file_name} 到 {target.host.name}",
                idempotency_scope=(
                    f"host:{target.host.id}:pool:{target.pool.id}:file:"
                    f"{copy_input.target_file_name}"
                ),
                idempotency_key=str(uuid4()),
                host_id=target.host.id,
                resource_type="media_image",
                resource_id=copy_input.media_item_id,
                total_steps=5,
                resumable=True,
                max_retries=3,
                recovery_strategy="retry_from_start",
                input_summary=copy_input.encode(),
            ),
        ),
    )
