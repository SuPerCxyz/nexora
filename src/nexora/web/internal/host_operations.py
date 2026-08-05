"""Session-only host resource discovery operations."""

from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from nexora.hosts.models import HostStatus
from nexora.hosts.read_service import HostReadService
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.read_service import TaskReadService
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import TaskCreatedResponse

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.post("/hosts/{host_id}/scan")
async def internal_host_scan(request: Request, host_id: str) -> JSONResponse:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    csrf_error = verify_internal_csrf(request)
    if csrf_error is not None:
        return csrf_error
    detail = HostReadService(request.app.state.database).detail(host_id)
    if detail is None:
        return internal_error(404, "host_not_found", "节点不存在")
    if detail.host.status not in {HostStatus.READY, HostStatus.DEGRADED}:
        return internal_error(409, "host_scan_blocked", "当前节点状态不允许重新扫描")
    task_reader = TaskReadService(request.app.state.database)
    for task_type in ("host.capability_probe", "host.resource_discovery"):
        active = task_reader.find_active(task_type, host_id=host_id)
        if active is not None:
            return _response(active.id, 200)
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="host.capability_probe",
            title=f"刷新节点 {detail.host.name}",
            idempotency_scope=f"host:{host_id}:capability-probe",
            idempotency_key=str(uuid4()),
            host_id=host_id,
            total_steps=22,
            resumable=False,
            recovery_strategy="verify_only",
        )
    )
    return _response(task.id, 201)


def _response(task_id: str, status_code: int) -> JSONResponse:
    payload = TaskCreatedResponse(task_id=task_id, location=f"/tasks/{task_id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=status_code))
