"""Session-only JSON API for VM delete and rename."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from nexora.resources.models import ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.vms.read_service import VmReadService
from nexora.vms.remove_contracts import VmRemoveInput
from nexora.vms.remove_service import VmRemoveError, VmRemoveService
from nexora.vms.remove_tasks import VmRemoveTaskInput
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import TaskCreatedResponse

router = APIRouter(prefix="/internal", include_in_schema=False)


class VmRemovePreviewRequest(BaseModel):
    operation: str = Field(min_length=1, max_length=16)
    target_name: str | None = Field(default=None, max_length=128)
    remove_disks: bool = False
    remove_nvram: bool = False


class VmRemoveApplyRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=64)
    confirmation_token: str = Field(min_length=1, max_length=128)
    confirmation_name: str = Field(min_length=1, max_length=128)


@router.post("/hosts/{host_id}/vms/{vm_uuid}/remove/preview")
async def preview_remove(
    request: Request,
    host_id: str,
    vm_uuid: str,
    submitted: VmRemovePreviewRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    detail = VmReadService(request.app.state.database).detail(host_id, vm_uuid)
    if detail is None or detail.resource.persistent_hash is None:
        return internal_error(404, "vm_not_found", "虚拟机不存在")
    if bool(detail.details.get("active")):
        return internal_error(409, "vm_remove_requires_shutdown", "删除或重命名要求虚拟机已关机")
    try:
        remove = VmRemoveInput(
            host_id=host_id,
            resource_id=detail.resource.id,
            vm_uuid=detail.resource.native_id,
            vm_name=detail.resource.display_name,
            generation=detail.resource.observed_generation,
            persistent_hash=detail.resource.persistent_hash,
            operation=submitted.operation,
            target_name=submitted.target_name,
            remove_disks=submitted.remove_disks,
            remove_nvram=submitted.remove_nvram,
        )
        service: VmRemoveService = request.app.state.vm_remove_service
        preview = await run_in_threadpool(service.preview, remove)
    except (TypeError, ValueError, VmRemoveError) as exc:
        return internal_error(422, "vm_remove_preview_failed", str(exc))
    return no_store(
        JSONResponse(
            {
                "plan_id": preview.plan.id,
                "confirmation_token": preview.confirmation_token,
                "operation": remove.operation,
                "target_name": remove.target_name,
                "remove_disks": remove.remove_disks,
                "remove_nvram": remove.remove_nvram,
                "diff_text": preview.plan.diff_text,
            }
        )
    )


@router.post("/hosts/{host_id}/vms/{vm_uuid}/remove/apply")
async def apply_remove(
    request: Request,
    host_id: str,
    vm_uuid: str,
    submitted: VmRemoveApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    service: VmRemoveService = request.app.state.vm_remove_service
    try:
        plan = await run_in_threadpool(
            service.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            host_id=host_id,
            vm_uuid=vm_uuid,
            confirmation_name=submitted.confirmation_name,
        )
    except (VmRemoveError, ValueError) as exc:
        return internal_error(409, "vm_remove_confirmation_failed", str(exc))
    title = "重命名" if plan.operation == "rename" else "删除"
    task_input = VmRemoveTaskInput(plan.id, plan.host_id, plan.vm_uuid)
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.remove",
            title=f"{title}虚拟机 · {plan.vm_name}",
            idempotency_scope=f"vm:{host_id}:{vm_uuid}:{plan.operation}",
            idempotency_key=plan.id,
            host_id=host_id,
            vm_uuid=vm_uuid,
            resource_type=ResourceType.VIRTUAL_MACHINE,
            resource_id=plan.vm_uuid,
            total_steps=3,
            resumable=False,
            recovery_strategy="verify_only",
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
