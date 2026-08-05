"""Session-only JSON APIs for VM snapshot changes."""

from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteConflict
from nexora.resources.models import ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.read_service import TaskReadService
from nexora.vms.contracts import VmChangeTaskInput
from nexora.vms.read_service import VmDetail, VmReadService
from nexora.vms.snapshot_contracts import (
    SnapshotCreateInput,
    SnapshotDeleteInput,
    SnapshotRevertInput,
)
from nexora.vms.snapshot_errors import SnapshotChangeError
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import TaskCreatedResponse

router = APIRouter(prefix="/internal", include_in_schema=False)


class SnapshotPreviewRequest(BaseModel):
    operation: Literal["create", "delete", "revert"]
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    snapshot_resource_id: str | None = Field(default=None, max_length=64)


class SnapshotApplyRequest(BaseModel):
    operation: Literal["create", "delete", "revert"]
    plan_id: str = Field(min_length=1, max_length=64)
    confirmation_token: str = Field(min_length=1, max_length=128)
    snapshot_name: str = Field(min_length=1, max_length=128)
    confirmation_name: str | None = Field(default=None, max_length=128)


@router.post("/hosts/{host_id}/vms/{domain_uuid}/snapshots/preview")
async def preview_snapshot(
    request: Request,
    host_id: str,
    domain_uuid: str,
    submitted: SnapshotPreviewRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return internal_error(404, "vm_not_found", "虚拟机不存在")
    try:
        preview = await _preview(request, detail, submitted)
    except (TypeError, ValueError, ResourceWriteConflict, SnapshotChangeError) as exc:
        return internal_error(422, "snapshot_preview_failed", str(exc))
    return no_store(
        JSONResponse(
            {
                "plan_id": preview.plan.id,
                "confirmation_token": preview.confirmation_token,
                "operation": submitted.operation,
                "snapshot_name": submitted.name,
                "diff_text": preview.plan.diff_text,
            }
        )
    )


@router.post("/hosts/{host_id}/vms/{domain_uuid}/snapshots/apply")
async def apply_snapshot(
    request: Request,
    host_id: str,
    domain_uuid: str,
    submitted: SnapshotApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return internal_error(404, "vm_not_found", "虚拟机不存在")
    active = TaskReadService(request.app.state.database).find_active_vm_write(
        host_id, detail.resource.native_id
    )
    if active is not None:
        return _task_response(active.id, 200)
    try:
        plan = await _confirm(request, detail, submitted)
    except SnapshotChangeError as exc:
        return internal_error(409, "snapshot_confirmation_failed", str(exc))
    title = {
        "create": "创建快照",
        "delete": "删除快照",
        "revert": "恢复快照",
    }[submitted.operation]
    task_input = VmChangeTaskInput(
        plan.id,
        host_id,
        detail.resource.native_id,
        f"snapshot_{submitted.operation}",
    )
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.snapshot_change",
            title=f"{title} · {submitted.snapshot_name}",
            idempotency_scope=f"vm:{host_id}:{detail.resource.native_id}:snapshot",
            idempotency_key=plan.id,
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
    return _task_response(task.id, 201)


async def _preview(
    request: Request,
    detail: VmDetail,
    submitted: SnapshotPreviewRequest,
) -> Any:
    vm_base = _vm_base(detail)
    if submitted.operation == "create":
        create = SnapshotCreateInput(vm_base, submitted.name.strip(), submitted.description)
        return await run_in_threadpool(request.app.state.vm_snapshot_service.preview_create, create)
    snapshot_base = _snapshot_base(request, detail, submitted.snapshot_resource_id, submitted.name)
    if submitted.operation == "delete":
        delete = SnapshotDeleteInput(vm_base, snapshot_base, submitted.name)
        return await run_in_threadpool(request.app.state.vm_snapshot_delete_service.preview, delete)
    revert = SnapshotRevertInput(vm_base, snapshot_base, submitted.name)
    return await run_in_threadpool(request.app.state.vm_snapshot_revert_service.preview, revert)


async def _confirm(
    request: Request,
    detail: VmDetail,
    submitted: SnapshotApplyRequest,
) -> Any:
    common = {
        "host_id": detail.host.id,
        "vm_uuid": detail.resource.native_id,
    }
    if submitted.operation == "create":
        return await run_in_threadpool(
            request.app.state.vm_snapshot_service.confirm_create,
            submitted.plan_id,
            submitted.confirmation_token,
            **common,
        )
    service = (
        request.app.state.vm_snapshot_delete_service
        if submitted.operation == "delete"
        else request.app.state.vm_snapshot_revert_service
    )
    kwargs = {**common, "snapshot_name": submitted.snapshot_name}
    if submitted.operation == "revert":
        kwargs["confirmation_name"] = submitted.confirmation_name or ""
    return await run_in_threadpool(
        service.confirm,
        submitted.plan_id,
        submitted.confirmation_token,
        **kwargs,
    )


def _detail(request: Request, host_id: str, domain_uuid: str) -> VmDetail | None:
    try:
        return VmReadService(request.app.state.database).detail(host_id, domain_uuid)
    except ValueError:
        return None


def _vm_base(detail: VmDetail) -> ResourceBaseVersion:
    if detail.resource.persistent_hash is None:
        raise ValueError("Snapshot requires a persistent VM")
    return ResourceBaseVersion(
        detail.resource.id,
        detail.host.id,
        ResourceType.VIRTUAL_MACHINE,
        detail.resource.native_id,
        detail.resource.observed_generation,
        detail.resource.persistent_hash,
        detail.resource.live_hash,
    )


def _snapshot_base(
    request: Request,
    detail: VmDetail,
    resource_id: str | None,
    name: str,
) -> ResourceBaseVersion:
    snapshot = next(
        (
            item.resource
            for item in VmReadService(request.app.state.database).snapshots(
                detail.host.id, detail.resource.native_id
            )
            if item.resource.id == resource_id and item.resource.display_name == name
        ),
        None,
    )
    if snapshot is None or snapshot.persistent_hash is None:
        raise ValueError("Snapshot base version is invalid")
    return ResourceBaseVersion(
        snapshot.id,
        detail.host.id,
        ResourceType.SNAPSHOT,
        snapshot.native_id,
        snapshot.observed_generation,
        snapshot.persistent_hash,
        None,
    )


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)


def _task_response(task_id: str, status_code: int) -> JSONResponse:
    payload = TaskCreatedResponse(task_id=task_id, location=f"/tasks/{task_id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=status_code))
