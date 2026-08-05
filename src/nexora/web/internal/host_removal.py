"""Session-only confirmed host removal APIs."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from nexora.hosts.removal import HostRemovalError, HostRemovalService
from nexora.hosts.removal_models import HostRemovalMode
from nexora.tasks.definitions import TaskCreate
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import TaskCreatedResponse

router = APIRouter(prefix="/internal", include_in_schema=False)


class HostRemovalPreviewRequest(BaseModel):
    mode: str = Field(max_length=32)


class HostRemovalApplyRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=64)
    confirmation_token: str = Field(min_length=1, max_length=128)
    confirmation_name: str = Field(min_length=1, max_length=128)


@router.post("/hosts/{host_id}/removal/preview")
async def internal_host_removal_preview(
    request: Request,
    host_id: str,
    submitted: HostRemovalPreviewRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    try:
        mode = HostRemovalMode(submitted.mode)
        service: HostRemovalService = request.app.state.host_removal_service
        preview = await run_in_threadpool(service.preview, host_id, mode)
    except (HostRemovalError, ValueError) as exc:
        return internal_error(422, "host_removal_preview_failed", str(exc))
    payload = {
        "plan_id": preview.plan.id,
        "confirmation_token": preview.confirmation_token,
        "host_id": host_id,
        "host_name": preview.plan.host_name,
        "mode": str(preview.plan.mode),
        "paths": list(preview.inventory.paths),
        "units": list(preview.inventory.units),
        "warnings": list(preview.inventory.warnings),
    }
    return no_store(JSONResponse(payload))


@router.post("/hosts/{host_id}/removal/apply")
async def internal_host_removal_apply(
    request: Request,
    host_id: str,
    submitted: HostRemovalApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    service: HostRemovalService = request.app.state.host_removal_service
    try:
        plan = await run_in_threadpool(
            service.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            submitted.confirmation_name,
            host_id,
        )
    except HostRemovalError as exc:
        return internal_error(409, "host_removal_confirmation_failed", str(exc))
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="host.remove",
            title=f"从 Nexora 移除节点 {plan.host_name}",
            idempotency_scope=f"host:{host_id}:remove",
            idempotency_key=plan.id,
            host_id=host_id,
            resource_type="host",
            resource_id=plan.id,
            total_steps=3,
            resumable=False,
            recovery_strategy="verify_only",
        )
    )
    payload = TaskCreatedResponse(task_id=task.id, location=f"/tasks/{task.id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=201))


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)
