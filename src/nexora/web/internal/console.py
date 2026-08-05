"""Session-only one-time virtual machine console credentials."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from nexora.consoles.service import ConsoleService, ConsoleUnavailableError
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)

router = APIRouter(prefix="/internal", include_in_schema=False)


class ConsoleCreateRequest(BaseModel):
    kind: str


@router.post("/hosts/{host_id}/vms/{domain_uuid}/console")
async def internal_console_create(
    request: Request,
    host_id: str,
    domain_uuid: str,
    submitted: ConsoleCreateRequest,
) -> JSONResponse:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    csrf_error = verify_internal_csrf(request)
    if csrf_error is not None:
        return csrf_error
    service: ConsoleService = request.app.state.console_service
    try:
        if submitted.kind == "serial":
            credentials = await run_in_threadpool(
                service.create_serial,
                resolved.identity,
                host_id,
                domain_uuid,
            )
        elif submitted.kind == "vnc":
            credentials = await run_in_threadpool(
                service.create_vnc,
                resolved.identity,
                host_id,
                domain_uuid,
            )
        else:
            return internal_error(422, "console_kind_invalid", "不支持的控制台类型")
    except ConsoleUnavailableError as exc:
        return internal_error(409, "console_unavailable", str(exc))
    payload = {
        "session_id": credentials.session_id,
        "token": credentials.token,
        "kind": submitted.kind,
        "vm_uuid": domain_uuid,
    }
    return no_store(JSONResponse(payload, status_code=201))
