"""Session-only host network topology and change APIs."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from nexora.hosts.read_service import HostReadService
from nexora.networking.service import NetworkTopologyService
from nexora.networking.topology_models import NetworkTopology
from nexora.networking.write_service import BridgeCreateInput, VlanCreateInput
from nexora.tasks.definitions import TaskCreate
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import TaskCreatedResponse

router = APIRouter(prefix="/internal", include_in_schema=False)


class BridgePreviewRequest(BaseModel):
    host_id: str = Field(min_length=1, max_length=128)
    bridge_name: str = Field(min_length=1, max_length=15)
    attach_iface: str | None = Field(default=None, max_length=15)
    migrate_ip_cidr: str | None = Field(default=None, max_length=64)


class VlanPreviewRequest(BaseModel):
    host_id: str = Field(min_length=1, max_length=128)
    parent_iface: str = Field(min_length=1, max_length=15)
    vlan_id: int = Field(ge=1, le=4094)
    vlan_name: str | None = Field(default=None, max_length=15)


class NetworkApplyRequest(BaseModel):
    host_id: str = Field(min_length=1, max_length=128)
    plan_id: str = Field(min_length=1, max_length=64)
    confirmation_token: str = Field(min_length=1, max_length=128)


@router.get("/networks")
async def internal_networks(
    request: Request,
    host_id: str | None = Query(default=None, max_length=128),
) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    hosts = HostReadService(request.app.state.database).list_hosts()
    selected_id = host_id or (hosts[0].id if hosts else None)
    topology = (
        NetworkTopologyService(request.app.state.database).get(selected_id) if selected_id else None
    )
    if host_id is not None and topology is None:
        return internal_error(404, "host_not_found", "节点不存在")
    payload = {
        "hosts": [{"id": host.id, "name": host.name} for host in hosts],
        "selected_host_id": selected_id,
        "topology": _topology_payload(topology) if topology is not None else None,
    }
    return no_store(JSONResponse(payload))


@router.post("/networks/bridge/preview")
async def internal_bridge_preview(
    request: Request, submitted: BridgePreviewRequest
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    change = BridgeCreateInput(
        bridge_name=submitted.bridge_name,
        attach_iface=submitted.attach_iface or None,
        migrate_ip_cidr=submitted.migrate_ip_cidr or None,
    )
    return await _preview(request, submitted.host_id, "bridge", change)


@router.post("/networks/vlan/preview")
async def internal_vlan_preview(request: Request, submitted: VlanPreviewRequest) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    change = VlanCreateInput(
        parent_iface=submitted.parent_iface,
        vlan_id=submitted.vlan_id,
        vlan_name=submitted.vlan_name or None,
    )
    return await _preview(request, submitted.host_id, "vlan", change)


@router.post("/networks/apply")
async def internal_network_apply(request: Request, submitted: NetworkApplyRequest) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    service = request.app.state.network_write_service
    try:
        plan = await run_in_threadpool(
            service.plans.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            host_id=submitted.host_id,
        )
    except Exception as exc:
        return internal_error(409, "network_confirmation_failed", str(exc))
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="network.change",
            title=f"网络变更 · {plan.change_type} · {plan.target_iface}",
            idempotency_scope=f"host:{submitted.host_id}:network:{plan.target_iface}",
            idempotency_key=plan.id,
            host_id=submitted.host_id,
            resource_type="host",
            resource_id=submitted.host_id,
            total_steps=2,
            resumable=False,
            recovery_strategy="verify_only",
            input_summary=f"{plan.id}:{submitted.host_id}:{plan.change_type}",
        )
    )
    payload = TaskCreatedResponse(task_id=task.id, location=f"/tasks/{task.id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=201))


async def _preview(
    request: Request,
    host_id: str,
    kind: str,
    change: BridgeCreateInput | VlanCreateInput,
) -> JSONResponse:
    service = request.app.state.network_write_service
    try:
        method = service.preview_bridge_create if kind == "bridge" else service.preview_vlan_create
        preview = await run_in_threadpool(method, host_id, change)
    except Exception as exc:
        return internal_error(422, "network_preview_failed", str(exc))
    return no_store(
        JSONResponse(
            {
                "plan_id": preview.plan.id,
                "confirmation_token": preview.confirmation_token,
                "host_id": host_id,
                "change_type": preview.plan.change_type,
                "target_iface": preview.plan.target_iface,
                "rollback_script": preview.plan.rollback_script,
            }
        )
    )


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)


def _topology_payload(topology: NetworkTopology) -> dict[str, object]:
    return {
        "host_id": topology.host_id,
        "warning_count": topology.warning_count,
        "nodes": [
            {
                "id": node.id,
                "label": node.label,
                "node_type": node.node_type,
                "status": node.status,
                "details": node.details,
                "warnings": list(node.warnings),
                "management": node.management,
                "default_route": node.default_route,
            }
            for node in topology.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "relation": edge.relation,
                "warnings": list(edge.warnings),
                "management": edge.management,
            }
            for edge in topology.edges
        ],
    }
