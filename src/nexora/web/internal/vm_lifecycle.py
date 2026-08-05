"""Session-only virtual machine lifecycle task submission."""

from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.read_service import TaskReadService
from nexora.vms.contracts import LifecycleAction, LifecycleTaskInput
from nexora.vms.read_service import VmReadService
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import TaskCreatedResponse

router = APIRouter(prefix="/internal", include_in_schema=False)
SUPPORTED_ACTIONS = frozenset(
    {
        LifecycleAction.START,
        LifecycleAction.SHUTDOWN,
        LifecycleAction.FORCE_OFF,
        LifecycleAction.REBOOT,
        LifecycleAction.FORCE_REBOOT,
        LifecycleAction.PAUSE,
        LifecycleAction.RESUME,
        LifecycleAction.MANAGED_SAVE,
        LifecycleAction.AUTOSTART_ENABLE,
        LifecycleAction.AUTOSTART_DISABLE,
    }
)
DANGEROUS_ACTIONS = frozenset({LifecycleAction.FORCE_OFF, LifecycleAction.FORCE_REBOOT})


class VmLifecycleRequest(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    confirmation_name: str | None = Field(default=None, max_length=128)


@router.post("/hosts/{host_id}/vms/{domain_uuid}/lifecycle")
async def internal_vm_lifecycle(
    request: Request,
    host_id: str,
    domain_uuid: str,
    submitted: VmLifecycleRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    detail = VmReadService(request.app.state.database).detail(host_id, domain_uuid)
    if detail is None:
        return internal_error(404, "vm_not_found", "虚拟机不存在")
    if str(detail.resource.status) not in {"managed", "transient"}:
        return internal_error(409, "vm_write_blocked", "虚拟机配置状态不允许写操作")
    try:
        action = LifecycleAction(submitted.action)
    except ValueError:
        return internal_error(422, "vm_lifecycle_invalid", "不支持的虚拟机操作")
    if action not in SUPPORTED_ACTIONS or not _action_allowed(action, detail.details):
        return internal_error(409, "vm_lifecycle_conflict", "当前虚拟机状态不允许此操作")
    if action in DANGEROUS_ACTIONS and submitted.confirmation_name != detail.resource.display_name:
        return internal_error(409, "vm_name_mismatch", "虚拟机名称确认不匹配")
    active = TaskReadService(request.app.state.database).find_active_vm_write(
        host_id, detail.resource.native_id
    )
    if active is not None:
        return _task_response(active.id, 200)
    base = ResourceBaseVersion(
        resource_id=detail.resource.id,
        host_id=host_id,
        resource_type=ResourceType.VIRTUAL_MACHINE,
        native_id=detail.resource.native_id,
        generation=detail.resource.observed_generation,
        persistent_hash=detail.resource.persistent_hash,
        live_hash=detail.resource.live_hash,
    )
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.lifecycle",
            title=f"{_action_title(action)} · {detail.resource.display_name}",
            idempotency_scope=f"vm:{host_id}:{detail.resource.native_id}:lifecycle",
            idempotency_key=str(uuid4()),
            host_id=host_id,
            vm_uuid=detail.resource.native_id,
            resource_type=ResourceType.VIRTUAL_MACHINE,
            resource_id=detail.resource.id,
            total_steps=3,
            resumable=False,
            recovery_strategy="verify_only",
            input_summary=LifecycleTaskInput(action, base).encode(),
        )
    )
    return _task_response(task.id, 201)


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)


def _action_allowed(action: LifecycleAction, details: dict[str, object]) -> bool:
    state = str(details.get("state", "unknown")).lower()
    active = bool(details.get("active"))
    persistent = bool(details.get("persistent"))
    allowed = {
        LifecycleAction.START: not active and persistent,
        LifecycleAction.SHUTDOWN: state == "running",
        LifecycleAction.FORCE_OFF: active,
        LifecycleAction.REBOOT: state == "running",
        LifecycleAction.FORCE_REBOOT: active,
        LifecycleAction.PAUSE: state == "running",
        LifecycleAction.RESUME: state == "paused",
        LifecycleAction.MANAGED_SAVE: active and persistent,
        LifecycleAction.AUTOSTART_ENABLE: persistent and not bool(details.get("autostart")),
        LifecycleAction.AUTOSTART_DISABLE: persistent and bool(details.get("autostart")),
    }
    return allowed[action]


def _action_title(action: LifecycleAction) -> str:
    return {
        LifecycleAction.START: "启动虚拟机",
        LifecycleAction.SHUTDOWN: "正常关机",
        LifecycleAction.FORCE_OFF: "强制关机",
        LifecycleAction.REBOOT: "正常重启",
        LifecycleAction.FORCE_REBOOT: "强制重启",
        LifecycleAction.PAUSE: "暂停虚拟机",
        LifecycleAction.RESUME: "恢复虚拟机",
        LifecycleAction.MANAGED_SAVE: "保存运行状态",
        LifecycleAction.AUTOSTART_ENABLE: "启用自动启动",
        LifecycleAction.AUTOSTART_DISABLE: "禁用自动启动",
    }[action]


def _task_response(task_id: str, status_code: int) -> JSONResponse:
    payload = TaskCreatedResponse(task_id=task_id, location=f"/tasks/{task_id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=status_code))
