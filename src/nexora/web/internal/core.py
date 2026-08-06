"""Read-only data endpoints for React core pages."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from nexora.hosts.metrics_history import HostMetricsHistoryStore
from nexora.hosts.models import HostStatus
from nexora.hosts.read_service import HostReadService
from nexora.storage.read_service import StorageReadService
from nexora.tasks.models import TaskStatus
from nexora.tasks.read_service import ACTIVE_TASK_STATUSES, TaskReadService
from nexora.vms.guest_agent import GuestAgentView
from nexora.vms.metrics_history import MetricsHistoryStore
from nexora.vms.read_service import VmReadService
from nexora.web.internal.auth import no_store, resolve_internal_identity
from nexora.web.internal.contracts import (
    GuestAgentResponse,
    HostListResponse,
    InternalError,
    OverviewSummary,
    VmListResponse,
)
from nexora.web.internal.detail_mappers import (
    host_detail_response,
    host_summary,
    vm_detail_response,
    vm_summary,
)

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.get("/overview")
async def internal_overview(request: Request) -> JSONResponse:
    denied = _authentication_error(request)
    if denied is not None:
        return denied
    hosts = HostReadService(request.app.state.database).list_hosts()
    virtual_machines = VmReadService(request.app.state.database).list_vms()
    tasks = TaskReadService(request.app.state.database).recent()
    storage = StorageReadService(request.app.state.database)
    vm_states = [item.details.get("state") for item in virtual_machines]
    vm_running = sum(state == "running" for state in vm_states)
    vm_paused = sum(state == "paused" for state in vm_states)
    payload = OverviewSummary(
        host_total=len(hosts),
        host_ready=sum(host.status == HostStatus.READY for host in hosts),
        host_synced=sum(host.last_scanned_at is not None for host in hosts),
        vm_total=len(virtual_machines),
        vm_running=vm_running,
        vm_paused=vm_paused,
        vm_stopped=len(virtual_machines) - vm_running - vm_paused,
        active_tasks=sum(task.status in ACTIVE_TASK_STATUSES for task in tasks),
        task_pending=sum(task.status in (TaskStatus.PENDING, TaskStatus.QUEUED) for task in tasks),
        failed_tasks=sum(task.status == TaskStatus.FAILED for task in tasks),
        storage_pool_total=len(storage.pools()),
        storage_volume_total=len(storage.volumes()),
    )
    return _response(payload)


@router.get("/hosts")
async def internal_hosts(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> JSONResponse:
    denied = _authentication_error(request)
    if denied is not None:
        return denied
    service = HostReadService(request.app.state.database)
    hosts = service.list_hosts(limit=page_size, offset=(page - 1) * page_size)
    payload = HostListResponse(
        items=[host_summary(host) for host in hosts],
        total=service.count_hosts(),
        page=page,
        page_size=page_size,
    )
    return _response(payload)


@router.get("/vms")
async def internal_vms(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    state: str | None = Query(None, max_length=32),
    host_id: str | None = Query(None, max_length=36),
) -> JSONResponse:
    denied = _authentication_error(request)
    if denied is not None:
        return denied
    service = VmReadService(request.app.state.database)
    virtual_machines = service.list_vms(
        limit=page_size,
        offset=(page - 1) * page_size,
        state=state,
        host_id=host_id,
    )
    payload = VmListResponse(
        items=[vm_summary(item, request.app.state.database) for item in virtual_machines],
        total=service.count_vms(state=state, host_id=host_id),
        page=page,
        page_size=page_size,
    )
    return _response(payload)


@router.get("/hosts/{host_id}")
async def internal_host_detail(request: Request, host_id: str) -> JSONResponse:
    denied = _authentication_error(request)
    if denied is not None:
        return denied
    detail = HostReadService(request.app.state.database).detail(host_id)
    if detail is None:
        return _not_found("host_not_found", "节点不存在")
    metrics = HostMetricsHistoryStore(request.app.state.database).query(host_id)
    payload = host_detail_response(detail, metrics, request.app.state.database)
    return _response(payload)


@router.get("/hosts/{host_id}/vms/{domain_uuid}")
async def internal_vm_detail(
    request: Request,
    host_id: str,
    domain_uuid: str,
) -> JSONResponse:
    denied = _authentication_error(request)
    if denied is not None:
        return denied
    try:
        service = VmReadService(request.app.state.database)
        detail = service.detail(host_id, domain_uuid)
    except ValueError:
        detail = None
    if detail is None:
        return _not_found("vm_not_found", "虚拟机不存在")
    payload = vm_detail_response(
        detail,
        service.snapshots(host_id, domain_uuid),
        MetricsHistoryStore(request.app.state.database).query(host_id, domain_uuid),
        request.app.state.database,
    )
    return _response(payload)


@router.get("/hosts/{host_id}/vms/{domain_uuid}/guest-agent")
async def internal_vm_guest_agent(
    request: Request,
    host_id: str,
    domain_uuid: str,
) -> JSONResponse:
    denied = _authentication_error(request)
    if denied is not None:
        return denied
    try:
        view = await run_in_threadpool(
            request.app.state.vm_guest_agent_service.read,
            host_id,
            domain_uuid,
        )
    except ValueError:
        return _not_found("vm_not_found", "虚拟机不存在")
    except RuntimeError:
        view = GuestAgentView("unavailable", True, message="Guest Agent 状态暂不可用")
    return _response(GuestAgentResponse.model_validate(view, from_attributes=True))


def _authentication_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    return resolved if isinstance(resolved, JSONResponse) else None


def _response(payload: BaseModel) -> JSONResponse:
    return no_store(JSONResponse(payload.model_dump(mode="json")))


def _not_found(code: str, message: str) -> JSONResponse:
    return no_store(
        JSONResponse(InternalError(code=code, message=message).model_dump(), status_code=404)
    )
