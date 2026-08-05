"""Structured CPU topology preview and confirmed task submission."""

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
from nexora.vms.cpu_changes import VmChangeError, VmCpuChangeService
from nexora.vms.read_service import VmDetail, VmReadService
from nexora.web.rendering import templates
from nexora.web.security import CSRF_COOKIE, SESSION_COOKIE
from nexora.xml import CpuTopologyChange

router = APIRouter(include_in_schema=False)


@router.post("/hosts/{host_id}/vms/{domain_uuid}/cpu/preview")
async def cpu_change_preview(request: Request, host_id: str, domain_uuid: str) -> Response:
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
        base = _base_version(detail, form)
        change = CpuTopologyChange(
            current_vcpus=_integer(form, "current_vcpus"),
            maximum_vcpus=_integer(form, "maximum_vcpus"),
            sockets=_integer(form, "sockets"),
            dies=_integer(form, "dies"),
            clusters=_integer(form, "clusters"),
            cores=_integer(form, "cores"),
            threads=_integer(form, "threads"),
        )
        service: VmCpuChangeService = request.app.state.vm_cpu_change_service
        preview = await run_in_threadpool(service.preview, base, change)
    except (TypeError, ValueError, ResourceWriteConflict, VmChangeError) as exc:
        return PlainTextResponse(str(exc), status_code=422)
    return templates.TemplateResponse(
        request=request,
        name="vms/cpu_preview.html",
        context={
            "administrator": identity,
            "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
            "vm": detail,
            "preview": preview,
            "change": change,
        },
    )


@router.post("/hosts/{host_id}/vms/{domain_uuid}/cpu/apply")
async def cpu_change_apply(request: Request, host_id: str, domain_uuid: str) -> Response:
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
    service: VmCpuChangeService = request.app.state.vm_cpu_change_service
    try:
        plan = await run_in_threadpool(
            service.confirm,
            str(form.get("plan_id", "")),
            str(form.get("confirmation_token", "")),
            host_id=host_id,
            vm_uuid=detail.resource.native_id,
            change_type="cpu_topology",
        )
    except VmChangeError as exc:
        return PlainTextResponse(str(exc), status_code=409)
    task_input = VmChangeTaskInput(
        plan.id,
        host_id,
        detail.resource.native_id,
        "cpu_topology",
    )
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.cpu_change",
            title=f"更新 CPU · {detail.resource.display_name}",
            idempotency_scope=f"vm:{host_id}:{detail.resource.native_id}:cpu",
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


def _detail(request: Request, host_id: str, domain_uuid: str) -> VmDetail | None:
    try:
        return VmReadService(request.app.state.database).detail(host_id, domain_uuid)
    except ValueError:
        return None


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


def _integer(form: FormData, name: str) -> int:
    value = int(str(form.get(name, "0")))
    if not 1 <= value <= 65_536:
        raise ValueError(f"{name} must be between 1 and 65536")
    return value


def _required_hash(value: object) -> str:
    text = str(value or "")
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError("persistent VM hash is invalid")
    return text


def _identity(request: Request) -> SessionIdentity | None:
    service: SessionService = request.app.state.session_service
    return service.resolve(request.cookies.get(SESSION_COOKIE))


def _valid_csrf(request: Request, submitted: object) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    service: SessionService = request.app.state.session_service
    return (
        token is not None and isinstance(submitted, str) and service.verify_csrf(token, submitted)
    )
