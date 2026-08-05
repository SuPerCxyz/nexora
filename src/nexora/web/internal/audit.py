"""Session-only redacted remote command audit API."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from nexora.audit.read_service import AuditReadService
from nexora.hosts.read_service import HostReadService
from nexora.web.internal.auth import internal_error, no_store, resolve_internal_identity

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.get("/audit")
async def internal_audit(
    request: Request,
    page: int = Query(default=1, ge=1, le=10_000),
    host_id: str | None = Query(default=None, max_length=128),
    outcome: str = Query(default="all", max_length=16),
) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    try:
        audit = AuditReadService(request.app.state.database).page(
            page=page,
            host_id=host_id,
            outcome=outcome,
        )
    except ValueError as exc:
        return internal_error(422, "audit_filter_invalid", str(exc))
    hosts = HostReadService(request.app.state.database).list_hosts()
    payload = {
        "items": [
            {
                "operation_id": item.operation_id,
                "host_id": item.host_id,
                "host_name": item.host_name,
                "command_summary": item.command_summary,
                "outcome": item.outcome,
                "exit_code": item.exit_code,
                "stdout_summary": item.stdout_summary,
                "stderr_summary": item.stderr_summary,
                "occurred_at": item.occurred_at.isoformat(),
            }
            for item in audit.items
        ],
        "page": audit.page,
        "total": audit.total,
        "has_previous": audit.has_previous,
        "has_next": audit.has_next,
        "hosts": [{"id": host.id, "name": host.name} for host in hosts],
        "selected_host_id": host_id,
        "selected_outcome": outcome,
    }
    return no_store(JSONResponse(payload))
