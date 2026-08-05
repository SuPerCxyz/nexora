"""Session-only JSON API for shutdown full VM cloning."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from nexora.resources.models import ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.vms.clone_authority import VmCloneConflict
from nexora.vms.clone_contracts import VmCloneManifest
from nexora.vms.clone_models import VmClonePlan
from nexora.vms.clone_service import VmCloneError
from nexora.vms.clone_tasks import VmCloneTaskInput
from nexora.vms.read_service import VmReadService
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import TaskCreatedResponse

router = APIRouter(prefix="/internal", include_in_schema=False)


class VmClonePreviewRequest(BaseModel):
    target_pool_id: str = Field(min_length=1, max_length=64)
    target_name: str = Field(min_length=1, max_length=127)


class VmMigrationPreviewRequest(BaseModel):
    target_pool_id: str = Field(min_length=1, max_length=64)


class VmCloneApplyRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=64)
    confirmation_token: str = Field(min_length=1, max_length=128)


@router.post("/hosts/{host_id}/vms/{vm_uuid}/clone/preview")
async def preview_clone(
    request: Request,
    host_id: str,
    vm_uuid: str,
    submitted: VmClonePreviewRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    detail = VmReadService(request.app.state.database).detail(host_id, vm_uuid)
    if detail is None or detail.resource.persistent_hash is None:
        return internal_error(404, "vm_not_found", "可克隆虚拟机不存在")
    if bool(detail.details.get("active")):
        return internal_error(409, "vm_clone_requires_shutdown", "完整克隆要求虚拟机已关机")
    try:
        preview = await run_in_threadpool(
            request.app.state.vm_clone_service.preview,
            source_host_id=host_id,
            source_vm_uuid=vm_uuid,
            source_resource_id=detail.resource.id,
            source_generation=detail.resource.observed_generation,
            source_hash=detail.resource.persistent_hash,
            target_pool_id=submitted.target_pool_id,
            target_name=submitted.target_name,
        )
    except (TypeError, ValueError, VmCloneError, VmCloneConflict) as exc:
        return internal_error(422, "vm_clone_preview_failed", str(exc))
    return no_store(
        JSONResponse(
            {
                "plan_id": preview.plan.id,
                "confirmation_token": preview.confirmation_token,
                "target_host_id": preview.manifest.target_host_id,
                "target_vm_uuid": preview.manifest.target_vm_uuid,
                "target_name": preview.manifest.target_name,
                "file_count": len(preview.manifest.files),
                "diff_text": preview.plan.diff_text,
            }
        )
    )


@router.post("/hosts/{host_id}/vms/{vm_uuid}/migrate/preview")
async def preview_migrate(
    request: Request,
    host_id: str,
    vm_uuid: str,
    submitted: VmMigrationPreviewRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    detail = VmReadService(request.app.state.database).detail(host_id, vm_uuid)
    if detail is None or detail.resource.persistent_hash is None:
        return internal_error(404, "vm_not_found", "可迁移虚拟机不存在")
    if bool(detail.details.get("active")):
        return internal_error(409, "vm_migrate_requires_shutdown", "关机迁移要求虚拟机已关机")
    try:
        preview = await run_in_threadpool(
            request.app.state.vm_clone_service.preview,
            source_host_id=host_id,
            source_vm_uuid=vm_uuid,
            source_resource_id=detail.resource.id,
            source_generation=detail.resource.observed_generation,
            source_hash=detail.resource.persistent_hash,
            target_pool_id=submitted.target_pool_id,
            target_name=detail.resource.display_name,
            preserve_identity=True,
        )
    except (TypeError, ValueError, VmCloneError, VmCloneConflict) as exc:
        return internal_error(422, "vm_migrate_preview_failed", str(exc))
    return no_store(
        JSONResponse(
            {
                "plan_id": preview.plan.id,
                "confirmation_token": preview.confirmation_token,
                "target_host_id": preview.manifest.target_host_id,
                "target_vm_uuid": preview.manifest.target_vm_uuid,
                "target_name": preview.manifest.target_name,
                "file_count": len(preview.manifest.files),
                "preserve_identity": True,
                "diff_text": preview.plan.diff_text,
            }
        )
    )


@router.post("/hosts/{host_id}/vms/{vm_uuid}/clone/apply")
async def apply_clone(
    request: Request,
    host_id: str,
    vm_uuid: str,
    submitted: VmCloneApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    try:
        plan = await run_in_threadpool(
            request.app.state.vm_clone_service.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            source_host_id=host_id,
            source_vm_uuid=vm_uuid,
        )
        manifest = VmCloneManifest.decode(plan.manifest_json)
    except (ValueError, VmCloneError, VmCloneConflict) as exc:
        return internal_error(409, "vm_clone_confirmation_failed", str(exc))
    return _enqueue_identity_task(request, plan, manifest, host_id, vm_uuid)


@router.post("/hosts/{host_id}/vms/{vm_uuid}/migrate/apply")
async def apply_migrate(
    request: Request,
    host_id: str,
    vm_uuid: str,
    submitted: VmCloneApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    try:
        plan = await run_in_threadpool(
            request.app.state.vm_clone_service.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            source_host_id=host_id,
            source_vm_uuid=vm_uuid,
        )
        manifest = VmCloneManifest.decode(plan.manifest_json)
    except (ValueError, VmCloneError, VmCloneConflict) as exc:
        return internal_error(409, "vm_migrate_confirmation_failed", str(exc))
    if not manifest.preserve_identity:
        return internal_error(409, "vm_migrate_identity_mismatch", "迁移计划身份不匹配")
    return _enqueue_identity_task(request, plan, manifest, host_id, vm_uuid, migrate=True)


def _enqueue_identity_task(
    request: Request,
    plan: VmClonePlan,
    manifest: VmCloneManifest,
    host_id: str,
    vm_uuid: str,
    *,
    migrate: bool = False,
) -> JSONResponse:
    task_input = VmCloneTaskInput(
        plan.id,
        manifest.source_host_id,
        manifest.source_vm_uuid,
        manifest.target_host_id,
        manifest.target_vm_uuid,
    )
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.clone",
            title=f"{'关机迁移' if migrate else '完整克隆'} · {plan.target_name}",
            idempotency_scope=(
                f"vm:{host_id}:{vm_uuid}:migrate" if migrate else f"vm:{host_id}:{vm_uuid}:clone"
            ),
            idempotency_key=plan.id,
            host_id=host_id,
            vm_uuid=vm_uuid,
            resource_type=ResourceType.VIRTUAL_MACHINE,
            resource_id=manifest.target_vm_uuid,
            total_steps=len(manifest.files) + 3,
            resumable=True,
            recovery_strategy="resume_from_checkpoint",
            input_summary=task_input.encode(),
        )
    )
    payload = TaskCreatedResponse(task_id=task.id, location=f"/tasks/{task.id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=201))


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)
