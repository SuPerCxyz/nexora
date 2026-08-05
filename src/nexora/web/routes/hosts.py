"""Internal server-rendered host onboarding pages."""

from uuid import uuid4

from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from nexora.auth.sessions import SessionIdentity, SessionService
from nexora.hosts.contracts import CredentialPayload, HostCreate
from nexora.hosts.metrics_history import HostMetricsHistoryStore
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.hosts.onboarding import (
    HostConfirmationError,
    HostKeyChangedError,
    HostOnboardingService,
)
from nexora.hosts.read_service import HostDetail, HostReadService
from nexora.remote.host_keys import HostKeyCandidate
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.models import Task
from nexora.tasks.queue import TaskQueue
from nexora.tasks.read_service import TaskReadService
from nexora.web.rendering import templates
from nexora.web.security import CSRF_COOKIE, SESSION_COOKIE

router = APIRouter(include_in_schema=False)


def _identity(request: Request) -> SessionIdentity | None:
    service: SessionService = request.app.state.session_service
    return service.resolve(request.cookies.get(SESSION_COOKIE))


def _csrf(request: Request) -> str:
    return request.cookies.get(CSRF_COOKIE, "")


@router.get("/hosts")
async def host_list(request: Request) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    hosts = HostReadService(request.app.state.database).list_hosts()
    return templates.TemplateResponse(
        request=request,
        name="hosts/list.html",
        context={
            "administrator": identity,
            "csrf_token": _csrf(request),
            "hosts": hosts,
        },
    )


@router.get("/hosts/new")
async def host_create_page(request: Request) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return _render_create(request, identity)


@router.post("/hosts")
async def host_create_submit(request: Request) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    try:
        authentication = AuthenticationMethod(str(form.get("authentication_method", "")))
        labels = tuple(
            label.strip() for label in str(form.get("labels", "")).split(",") if label.strip()
        )
        create = HostCreate(
            name=str(form.get("name", "")),
            address=str(form.get("address", "")),
            ssh_port=int(str(form.get("ssh_port", "22"))),
            ssh_username=str(form.get("ssh_username", "")),
            authentication_method=authentication,
            credential=CredentialPayload(
                password=str(form.get("password", "")) or None,
                private_key=str(form.get("private_key", "")) or None,
                private_key_passphrase=str(form.get("private_key_passphrase", "")) or None,
            ),
            sudo_mode=SudoMode(str(form.get("sudo_mode", ""))),
            labels=labels,
            notes=str(form.get("notes", "")) or None,
        )
        service: HostOnboardingService = request.app.state.host_onboarding_service
        host = await run_in_threadpool(service.begin, create)
    except (RuntimeError, ValueError) as exc:
        return _render_create(
            request,
            identity,
            error=str(exc),
            status_code=422,
            form_values={
                "name": str(form.get("name", "")),
                "address": str(form.get("address", "")),
                "ssh_port": str(form.get("ssh_port", "22")),
                "ssh_username": str(form.get("ssh_username", "")),
                "authentication_method": str(form.get("authentication_method", "private_key")),
                "sudo_mode": str(form.get("sudo_mode", "passwordless")),
                "labels": str(form.get("labels", "")),
                "notes": str(form.get("notes", "")),
            },
        )
    return RedirectResponse(
        f"/hosts/{host.id}/confirm",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/hosts/{host_id}")
@router.get("/manage/hosts/{host_id}")
async def host_detail(request: Request, host_id: str) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    detail = HostReadService(request.app.state.database).detail(host_id)
    if detail is None:
        return PlainTextResponse("Host not found", status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="hosts/detail.html",
        context={
            "administrator": identity,
            "csrf_token": _csrf(request),
            "detail": detail,
            "metrics_history": HostMetricsHistoryStore(request.app.state.database).query(host_id),
        },
    )


@router.post("/hosts/{host_id}/scan")
async def host_scan_submit(request: Request, host_id: str) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    detail = HostReadService(request.app.state.database).detail(host_id)
    if detail is None:
        return PlainTextResponse("Host not found", status_code=404)
    if detail.host.status not in {HostStatus.READY, HostStatus.DEGRADED}:
        return PlainTextResponse("Host is not ready for scanning", status_code=409)
    queue: TaskQueue = request.app.state.task_queue
    active = TaskReadService(request.app.state.database).find_active(
        "host.resource_discovery",
        host_id=host_id,
    )
    if active is None:
        queue.enqueue(
            TaskCreate(
                task_type="host.resource_discovery",
                title=f"重新扫描节点 {detail.host.name}",
                idempotency_scope=f"host:{host_id}:resource-discovery",
                idempotency_key=str(uuid4()),
                host_id=host_id,
                total_steps=6,
                resumable=False,
                recovery_strategy="verify_only",
            )
        )
    return RedirectResponse(f"/hosts/{host_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/hosts/{host_id}/confirm")
async def host_confirm_page(request: Request, host_id: str) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    detail = HostReadService(request.app.state.database).detail(host_id)
    if detail is None or detail.host.pending_host_key_digest is None:
        return RedirectResponse(f"/hosts/{host_id}", status_code=status.HTTP_303_SEE_OTHER)
    return _render_confirm(request, identity, detail)


@router.post("/hosts/{host_id}/confirm")
async def host_confirm_submit(request: Request, host_id: str) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    service: HostOnboardingService = request.app.state.host_onboarding_service
    try:
        host = await run_in_threadpool(
            service.confirm,
            host_id,
            str(form.get("host_key_digest", "")),
        )
    except HostKeyChangedError as exc:
        detail = HostReadService(request.app.state.database).detail(host_id)
        if detail is None:
            return PlainTextResponse("Host not found", status_code=404)
        return _render_confirm(
            request,
            identity,
            detail,
            error=str(exc),
            changed_current=exc.current,
            status_code=409,
        )
    except HostConfirmationError as exc:
        detail = HostReadService(request.app.state.database).detail(host_id)
        if detail is None:
            return PlainTextResponse("Host not found", status_code=404)
        return _render_confirm(request, identity, detail, error=str(exc), status_code=422)
    enqueue_host_probe(request, host)
    return RedirectResponse(f"/hosts/{host.id}", status_code=status.HTTP_303_SEE_OTHER)


def enqueue_host_probe(request: Request, host: Host) -> Task:
    queue: TaskQueue = request.app.state.task_queue
    return queue.enqueue(
        TaskCreate(
            task_type="host.capability_probe",
            title=f"探测节点 {host.name}",
            idempotency_scope=f"host:{host.id}:initial-probe",
            idempotency_key="v1",
            host_id=host.id,
            total_steps=22,
            resumable=False,
            recovery_strategy="verify_only",
        )
    )


def _valid_csrf(request: Request, submitted: object) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    service: SessionService = request.app.state.session_service
    return (
        token is not None and isinstance(submitted, str) and service.verify_csrf(token, submitted)
    )


def _render_create(
    request: Request,
    identity: SessionIdentity,
    *,
    error: str | None = None,
    status_code: int = 200,
    form_values: dict[str, str] | None = None,
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="hosts/create.html",
        context={
            "administrator": identity,
            "csrf_token": _csrf(request),
            "error": error,
            "form_values": form_values or {},
        },
        status_code=status_code,
    )


def _render_confirm(
    request: Request,
    identity: SessionIdentity,
    detail: HostDetail,
    *,
    error: str | None = None,
    changed_current: list[HostKeyCandidate] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="hosts/confirm.html",
        context={
            "administrator": identity,
            "csrf_token": _csrf(request),
            "detail": detail,
            "error": error,
            "changed_current": changed_current or [],
        },
        status_code=status_code,
    )
