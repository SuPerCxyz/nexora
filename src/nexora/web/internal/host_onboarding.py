"""Session-only API for two-stage managed host onboarding."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from nexora.hosts.contracts import CredentialPayload, HostCreate
from nexora.hosts.models import AuthenticationMethod, SudoMode
from nexora.hosts.onboarding import (
    HostConfirmationError,
    HostKeyChangedError,
    HostOnboardingService,
)
from nexora.hosts.read_service import HostReadService
from nexora.web.internal.auth import no_store, resolve_internal_identity, verify_internal_csrf
from nexora.web.internal.contracts import (
    HostKeyConfirmationResponse,
    HostKeyConfirmRequest,
    HostKeySummary,
    HostOnboardingRequest,
    HostOnboardingStartedResponse,
    InternalError,
    TaskCreatedResponse,
)
from nexora.web.routes.hosts import enqueue_host_probe

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.post("/hosts/onboarding")
async def begin_host_onboarding(
    request: Request,
    submitted: HostOnboardingRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    try:
        create = HostCreate(
            name=submitted.name,
            address=submitted.address,
            ssh_port=submitted.ssh_port,
            ssh_username=submitted.ssh_username,
            authentication_method=AuthenticationMethod(submitted.authentication_method),
            credential=CredentialPayload(
                password=submitted.password,
                private_key=submitted.private_key,
                private_key_passphrase=submitted.private_key_passphrase,
            ),
            sudo_mode=SudoMode(submitted.sudo_mode),
            labels=tuple(submitted.labels),
            notes=submitted.notes,
        )
        service: HostOnboardingService = request.app.state.host_onboarding_service
        host = await run_in_threadpool(service.begin, create)
    except (RuntimeError, ValueError) as exc:
        return _error(422, "host_onboarding_failed", str(exc))
    payload = HostOnboardingStartedResponse(
        host_id=host.id,
        location=f"/hosts/{host.id}/confirm",
    )
    return no_store(JSONResponse(payload.model_dump(), status_code=201))


@router.get("/hosts/{host_id}/host-key-confirmation")
async def host_key_confirmation(request: Request, host_id: str) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    detail = HostReadService(request.app.state.database).detail(host_id)
    if detail is None:
        return _error(404, "host_not_found", "节点不存在")
    digest = detail.host.pending_host_key_digest
    if digest is None:
        return _error(409, "host_not_pending", "节点不再等待 Host Key 确认")
    payload = HostKeyConfirmationResponse(
        host_id=host_id,
        name=detail.host.name,
        endpoint=f"{detail.host.address}:{detail.host.ssh_port}",
        host_key_digest=digest,
        fingerprints=[
            HostKeySummary(key_type=item.key_type, fingerprint=item.fingerprint)
            for item in detail.fingerprints
        ],
    )
    return no_store(JSONResponse(payload.model_dump()))


@router.post("/hosts/{host_id}/host-key-confirmation")
async def confirm_host_key(
    request: Request,
    host_id: str,
    submitted: HostKeyConfirmRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    service: HostOnboardingService = request.app.state.host_onboarding_service
    try:
        host = await run_in_threadpool(service.confirm, host_id, submitted.host_key_digest)
    except HostKeyChangedError as exc:
        current = [
            HostKeySummary(key_type=item.key_type, fingerprint=item.fingerprint).model_dump()
            for item in exc.current
        ]
        return _error(409, "host_key_changed", str(exc), conflict={"current": current})
    except HostConfirmationError as exc:
        return _error(422, "host_confirmation_failed", str(exc))
    task = enqueue_host_probe(request, host)
    payload = TaskCreatedResponse(task_id=task.id, location=f"/hosts/{host.id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=201))


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)


def _error(
    status_code: int,
    code: str,
    message: str,
    *,
    conflict: dict[str, object] | None = None,
) -> JSONResponse:
    payload = InternalError(code=code, message=message, conflict=conflict)
    return no_store(JSONResponse(payload.model_dump(), status_code=status_code))
