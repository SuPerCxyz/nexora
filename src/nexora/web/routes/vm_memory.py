"""Structured memory preview and confirmed task submission."""

from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData
from starlette.responses import Response

from nexora.auth.sessions import SessionIdentity, SessionService
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteConflict
from nexora.resources.models import ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.read_service import TaskReadService
from nexora.vms.contracts import VmChangeTaskInput
from nexora.vms.cpu_changes import VmChangeError
from nexora.vms.memory_changes import VmMemoryChangeService
from nexora.vms.read_service import VmDetail, VmReadService
from nexora.web.rendering import templates
from nexora.web.security import CSRF_COOKIE, SESSION_COOKIE
from nexora.xml import MemoryConfigChange

router = APIRouter(include_in_schema=False)
MAX_MEMORY_MIB = 1_073_741_824


@router.post("/hosts/{host_id}/vms/{domain_uuid}/memory/preview")
async def memory_change_preview(
    request: Request,
    host_id: str,
    domain_uuid: str,
) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return PlainTextResponse("Virtual machine not found", status_code=404)
    try:
        change = _memory_change(form)
        service: VmMemoryChangeService = request.app.state.vm_memory_change_service
        preview = await run_in_threadpool(
            service.preview_memory,
            _base_version(detail, form),
            change,
        )
    except (TypeError, ValueError, ResourceWriteConflict, VmChangeError) as exc:
        return PlainTextResponse(str(exc), status_code=422)
    return templates.TemplateResponse(
        request=request,
        name="vms/memory_preview.html",
        context={
            "administrator": identity,
            "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
            "vm": detail,
            "preview": preview,
            "change": change,
        },
    )


@router.post("/hosts/{host_id}/vms/{domain_uuid}/memory/apply")
async def memory_change_apply(request: Request, host_id: str, domain_uuid: str) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return PlainTextResponse("Virtual machine not found", status_code=404)
    active = TaskReadService(request.app.state.database).find_active_vm_write(
        host_id,
        detail.resource.native_id,
    )
    if active is not None:
        return RedirectResponse(f"/tasks/{active.id}", status_code=status.HTTP_303_SEE_OTHER)
    service: VmMemoryChangeService = request.app.state.vm_memory_change_service
    try:
        plan = await run_in_threadpool(
            service.confirm,
            str(form.get("plan_id", "")),
            str(form.get("confirmation_token", "")),
            host_id=host_id,
            vm_uuid=detail.resource.native_id,
            change_type="memory_config",
        )
    except VmChangeError as exc:
        return PlainTextResponse(str(exc), status_code=409)
    task_input = VmChangeTaskInput(
        plan.id,
        host_id,
        detail.resource.native_id,
        "memory_config",
    )
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.memory_change",
            title=f"更新内存 · {detail.resource.display_name}",
            idempotency_scope=f"vm:{host_id}:{detail.resource.native_id}:memory",
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
    return RedirectResponse(f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


def _memory_change(form: FormData) -> MemoryConfigChange:
    return MemoryConfigChange(
        current_kib=_mib(form, "current_mib") * 1024,
        maximum_kib=_mib(form, "maximum_mib") * 1024,
        hugepages=form.get("hugepages") == "on",
        locked=form.get("locked") == "on",
        source_type=_optional_choice(form, "source_type"),
        access_mode=_optional_choice(form, "access_mode"),
        allocation_mode=_optional_choice(form, "allocation_mode"),
        discard=form.get("discard") == "on",
    )


def _base_version(detail: VmDetail, form: FormData) -> ResourceBaseVersion:
    resource_id = str(form.get("resource_id", ""))
    generation = int(str(form.get("generation", "0")))
    persistent_hash = _required_hash(form.get("persistent_hash"))
    if resource_id != detail.resource.id or generation < 1:
        raise ValueError("VM base version is invalid")
    return ResourceBaseVersion(
        resource_id,
        detail.host.id,
        ResourceType.VIRTUAL_MACHINE,
        detail.resource.native_id,
        generation,
        persistent_hash,
        None,
    )


def _mib(form: FormData, name: str) -> int:
    value = int(str(form.get(name, "0")))
    if not 1 <= value <= MAX_MEMORY_MIB:
        raise ValueError(f"{name} is outside the supported range")
    return value


def _optional_choice(form: FormData, name: str) -> str | None:
    value = str(form.get(name, "")).strip()
    if len(value) > 32:
        raise ValueError(f"{name} is invalid")
    return value or None


def _required_hash(value: object) -> str:
    text = str(value or "")
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError("persistent VM hash is invalid")
    return text


def _detail(request: Request, host_id: str, domain_uuid: str) -> VmDetail | None:
    try:
        return VmReadService(request.app.state.database).detail(host_id, domain_uuid)
    except ValueError:
        return None


def _identity(request: Request) -> SessionIdentity | None:
    service: SessionService = request.app.state.session_service
    return service.resolve(request.cookies.get(SESSION_COOKIE))


def _valid_csrf(request: Request, submitted: object) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    service: SessionService = request.app.state.session_service
    return (
        token is not None and isinstance(submitted, str) and service.verify_csrf(token, submitted)
    )
