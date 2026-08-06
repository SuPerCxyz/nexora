"""Session-only task center APIs."""

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from nexora.db import Database
from nexora.hosts.models import Host
from nexora.tasks.models import Task, TaskStep
from nexora.tasks.read_service import TaskReadService
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import TaskCreatedResponse

router = APIRouter(prefix="/internal", include_in_schema=False)


class TaskSummary(BaseModel):
    id: str
    title: str
    task_type: str
    status: str
    progress: float
    current_step: int
    total_steps: int
    message: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    resumable: bool
    retry_count: int
    max_retries: int
    host_id: str | None = None
    host_name: str | None = None


class TaskStepSummary(BaseModel):
    sequence: int
    name: str
    status: str
    attempt_count: int
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None


class TaskDetailResponse(BaseModel):
    task: TaskSummary
    steps: list[TaskStepSummary]


@router.get("/tasks")
async def internal_tasks(request: Request) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    tasks = TaskReadService(request.app.state.database).recent()
    host_names = _host_names(request.app.state.database)
    payload = [_task_summary(task, host_names).model_dump(mode="json") for task in tasks]
    return no_store(JSONResponse({"items": payload}))


@router.get("/tasks/{task_id}")
async def internal_task_detail(request: Request, task_id: str) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    detail = TaskReadService(request.app.state.database).detail(task_id)
    if detail is None:
        return internal_error(404, "task_not_found", "任务不存在")
    payload = TaskDetailResponse(
        task=_task_summary(detail.task),
        steps=[_step_summary(step) for step in detail.steps],
    )
    return no_store(JSONResponse(payload.model_dump(mode="json")))


@router.post("/tasks/{task_id}/cancel")
async def internal_task_cancel(request: Request, task_id: str) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    if not request.app.state.task_queue.request_cancel(task_id):
        return internal_error(409, "task_cancel_rejected", "当前任务无法取消")
    return _task_location(task_id)


@router.post("/tasks/{task_id}/recover")
async def internal_task_recover(request: Request, task_id: str) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    if not request.app.state.task_queue.request_recovery(task_id):
        return internal_error(409, "task_recovery_rejected", "当前任务无法恢复")
    return _task_location(task_id)


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)


def _task_location(task_id: str) -> JSONResponse:
    payload = TaskCreatedResponse(task_id=task_id, location=f"/tasks/{task_id}")
    return no_store(JSONResponse(payload.model_dump()))


def _task_summary(task: Task, host_names: dict[str, str] | None = None) -> TaskSummary:
    names = host_names or {}
    return TaskSummary(
        id=task.id,
        title=task.title,
        task_type=task.task_type,
        status=str(task.status),
        progress=task.progress,
        current_step=task.current_step,
        total_steps=task.total_steps,
        message=task.message,
        error_message=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        resumable=task.resumable,
        retry_count=task.retry_count,
        max_retries=task.max_retries,
        host_id=task.host_id,
        host_name=names.get(task.host_id or ""),
    )


def _host_names(database: Database) -> dict[str, str]:
    with database.session() as session:
        rows = session.execute(select(Host.id, Host.name))
        return {host_id: name for host_id, name in rows}


def _step_summary(step: TaskStep) -> TaskStepSummary:
    return TaskStepSummary(
        sequence=step.sequence,
        name=step.name,
        status=str(step.status),
        attempt_count=step.attempt_count,
        started_at=step.started_at,
        finished_at=step.finished_at,
        error_code=step.error_code,
    )
