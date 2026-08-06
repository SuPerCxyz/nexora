"""JSON preview and apply endpoints for persistent VM configuration changes."""

from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteConflict
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.models import Task
from nexora.tasks.read_service import TaskReadService
from nexora.vms.contracts import VmChangeTaskInput
from nexora.vms.cpu_changes import VmChangeError
from nexora.vms.read_service import VmDetail, VmReadService
from nexora.vms.xml_history import VmXmlHistoryStore
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.internal.contracts import TaskCreatedResponse
from nexora.web.routes.vm_advanced import (
    _advanced_device_change,
    _cputune_change,
    _numa_change,
)
from nexora.web.routes.vm_cpu import _integer
from nexora.web.routes.vm_memory import _memory_change
from nexora.xml import CpuTopologyChange, DiskDetachChange

router = APIRouter(prefix="/internal", include_in_schema=False)


class VmChangePreviewRequest(BaseModel):
    operation: str = Field(min_length=1, max_length=64)
    values: dict[str, Any] = Field(default_factory=dict)


class VmChangeApplyRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=64)
    confirmation_token: str = Field(min_length=1, max_length=128)
    change_type: str = Field(min_length=1, max_length=64)


class VmChangeRollbackRequest(BaseModel):
    history_id: str = Field(min_length=1, max_length=36)


@router.post("/hosts/{host_id}/vms/{domain_uuid}/configuration/preview")
async def preview_vm_change(
    request: Request,
    host_id: str,
    domain_uuid: str,
    submitted: VmChangePreviewRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return internal_error(404, "vm_not_found", "虚拟机不存在")
    try:
        preview = await _preview(request, detail, submitted.operation, submitted.values)
    except (TypeError, ValueError, ResourceWriteConflict, VmChangeError) as exc:
        return internal_error(422, "vm_change_preview_failed", str(exc))
    return no_store(
        JSONResponse(
            {
                "plan_id": preview.plan.id,
                "confirmation_token": preview.confirmation_token,
                "change_type": preview.plan.change_type,
                "diff_text": preview.plan.diff_text,
            }
        )
    )


@router.post("/hosts/{host_id}/vms/{domain_uuid}/configuration/apply")
async def apply_vm_change(
    request: Request,
    host_id: str,
    domain_uuid: str,
    submitted: VmChangeApplyRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return internal_error(404, "vm_not_found", "虚拟机不存在")
    active = TaskReadService(request.app.state.database).find_active_vm_write(
        host_id, detail.resource.native_id
    )
    if active is not None:
        return _task_response(active.id, 200)
    settings = _task_settings(request, submitted.change_type)
    if settings is None:
        return internal_error(422, "vm_change_type_invalid", "不支持的配置变更类型")
    service, task_type, title, scope, total_steps = settings
    try:
        plan = await run_in_threadpool(
            service.confirm,
            submitted.plan_id,
            submitted.confirmation_token,
            host_id=host_id,
            vm_uuid=detail.resource.native_id,
            change_type=submitted.change_type,
        )
    except VmChangeError as exc:
        return internal_error(409, "vm_change_confirmation_failed", str(exc))
    task = _enqueue_change_task(request, detail, plan, task_type, title, scope, total_steps)
    return _task_response(task.id, 201)


@router.post("/hosts/{host_id}/vms/{domain_uuid}/configuration/save")
async def save_vm_change(
    request: Request,
    host_id: str,
    domain_uuid: str,
    submitted: VmChangePreviewRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return internal_error(404, "vm_not_found", "虚拟机不存在")
    active = TaskReadService(request.app.state.database).find_active_vm_write(
        host_id, detail.resource.native_id
    )
    if active is not None:
        return _task_response(active.id, 200)
    try:
        preview = await _preview(request, detail, submitted.operation, submitted.values)
    except (TypeError, ValueError, ResourceWriteConflict, VmChangeError) as exc:
        return internal_error(422, "vm_change_save_failed", str(exc))
    _snapshot_before_save(request, detail)
    settings = _task_settings(request, preview.plan.change_type)
    if settings is None:
        return internal_error(422, "vm_change_type_invalid", "不支持的配置变更类型")
    service, task_type, title, scope, total_steps = settings
    try:
        plan = await run_in_threadpool(
            service.confirm,
            preview.plan.id,
            preview.confirmation_token,
            host_id=host_id,
            vm_uuid=detail.resource.native_id,
            change_type=preview.plan.change_type,
        )
    except VmChangeError as exc:
        return internal_error(409, "vm_change_confirmation_failed", str(exc))
    task = _enqueue_change_task(request, detail, plan, task_type, title, scope, total_steps)
    return _task_response(task.id, 201)


@router.get("/hosts/{host_id}/vms/{domain_uuid}/configuration/history")
async def vm_configuration_history(
    request: Request,
    host_id: str,
    domain_uuid: str,
) -> JSONResponse:
    denied = resolve_internal_identity(request)
    if isinstance(denied, JSONResponse):
        return denied
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return internal_error(404, "vm_not_found", "虚拟机不存在")
    snapshots = VmXmlHistoryStore(request.app.state.database).list(
        host_id, detail.resource.native_id
    )
    payload = {
        "items": [
            {
                "id": snapshot.id,
                "created_at": snapshot.created_at.isoformat(),
                "xml_hash": snapshot.xml_hash,
            }
            for snapshot in snapshots
        ]
    }
    return no_store(JSONResponse(payload))


def _snapshot_before_save(request: Request, detail: VmDetail) -> None:
    persistent_xml = detail.documents.get("persistent_xml")
    if persistent_xml:
        VmXmlHistoryStore(request.app.state.database).record(
            detail.host.id, detail.resource.native_id, persistent_xml
        )


@router.post("/hosts/{host_id}/vms/{domain_uuid}/configuration/rollback")
async def rollback_vm_change(
    request: Request,
    host_id: str,
    domain_uuid: str,
    submitted: VmChangeRollbackRequest,
) -> JSONResponse:
    denied = _write_error(request)
    if denied is not None:
        return denied
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return internal_error(404, "vm_not_found", "虚拟机不存在")
    store = VmXmlHistoryStore(request.app.state.database)
    snapshot = store.get(submitted.history_id)
    if (
        snapshot is None
        or snapshot.host_id != host_id
        or snapshot.vm_uuid != detail.resource.native_id
    ):
        return internal_error(404, "vm_history_not_found", "配置历史快照不存在")
    active = TaskReadService(request.app.state.database).find_active_vm_write(
        host_id, detail.resource.native_id
    )
    if active is not None:
        return _task_response(active.id, 200)
    _snapshot_before_save(request, detail)
    task = cast(
        Task,
        request.app.state.task_queue.enqueue(
            TaskCreate(
                task_type="vm.xml_restore",
                title=f"回滚配置 · {detail.resource.display_name}",
                idempotency_scope=f"vm:{host_id}:{detail.resource.native_id}:xml-restore",
                idempotency_key=submitted.history_id,
                host_id=host_id,
                vm_uuid=detail.resource.native_id,
                resource_type=ResourceType.VIRTUAL_MACHINE,
                resource_id=detail.resource.id,
                total_steps=3,
                resumable=False,
                recovery_strategy="verify_only",
                input_summary=submitted.history_id,
            )
        ),
    )
    return _task_response(task.id, 201)


def _enqueue_change_task(
    request: Request,
    detail: VmDetail,
    plan: Any,
    task_type: str,
    title: str,
    scope: str,
    total_steps: int,
) -> Task:
    task_input = VmChangeTaskInput(
        plan.id, detail.host.id, detail.resource.native_id, plan.change_type
    )
    return cast(
        Task,
        request.app.state.task_queue.enqueue(
            TaskCreate(
                task_type=task_type,
                title=f"{title} · {detail.resource.display_name}",
                idempotency_scope=f"vm:{detail.host.id}:{detail.resource.native_id}:{scope}",
                idempotency_key=plan.id,
                host_id=detail.host.id,
                vm_uuid=detail.resource.native_id,
                resource_type=ResourceType.VIRTUAL_MACHINE,
                resource_id=detail.resource.id,
                total_steps=total_steps,
                resumable=False,
                recovery_strategy="verify_only",
                input_summary=task_input.encode(),
            )
        ),
    )


async def _preview(
    request: Request,
    detail: VmDetail,
    operation: str,
    values: dict[str, Any],
) -> Any:
    form = _form(detail, values)
    base = _base(detail)
    state = request.app.state
    if operation == "cpu":
        names = (
            "current_vcpus",
            "maximum_vcpus",
            "sockets",
            "dies",
            "clusters",
            "cores",
            "threads",
        )
        change = CpuTopologyChange(**{name: _integer(form, name) for name in names})
        return await run_in_threadpool(state.vm_cpu_change_service.preview, base, change)
    if operation == "memory":
        return await run_in_threadpool(
            state.vm_memory_change_service.preview_memory, base, _memory_change(form)
        )
    return await _preview_device_change(request, detail, operation, values)


async def _preview_device_change(
    request: Request,
    detail: VmDetail,
    operation: str,
    values: dict[str, Any],
) -> Any:
    state = request.app.state
    base = _base(detail)
    if operation == "disk_attach":
        volume = _resource_base(request, detail.host.id, values, "volume")
        return await run_in_threadpool(
            state.vm_disk_change_service.preview_attach,
            base,
            volume,
            bus=str(values.get("bus", "")),
            cache=_optional(values, "cache"),
            io=_optional(values, "io"),
            discard=_optional(values, "discard"),
            serial=_optional(values, "serial"),
            readonly=bool(values.get("readonly")),
            shareable=bool(values.get("shareable")),
            live=bool(values.get("live")),
        )
    if operation == "disk_detach":
        names = ("target", "bus", "device", "source")
        change = DiskDetachChange(*[str(values.get(name, "")) for name in names])
        return await run_in_threadpool(
            state.vm_disk_change_service.preview_detach,
            base,
            change,
            live=bool(values.get("live")),
        )
    if operation == "interface_attach":
        return await run_in_threadpool(
            state.vm_network_change_service.preview_attach,
            base,
            kind=str(values.get("kind", "")),
            source=str(values.get("source", "")),
            model=str(values.get("model", "virtio")),
            mac=_optional(values, "mac"),
            live=bool(values.get("live")),
        )
    if operation == "interface_detach":
        return await run_in_threadpool(
            state.vm_network_change_service.preview_detach,
            base,
            mac=str(values.get("mac", "")),
            live=bool(values.get("live")),
        )
    if operation == "interface_update":
        return await run_in_threadpool(
            state.vm_network_change_service.preview_update,
            base,
            mac=str(values.get("mac", "")),
            kind=_optional(values, "kind"),
            source=_optional(values, "source"),
            model=_optional(values, "model"),
            new_mac=_optional(values, "new_mac"),
            live=bool(values.get("live")),
        )
    if operation == "cdrom_add":
        return await run_in_threadpool(
            state.vm_cdrom_change_service.preview_add,
            base,
            bus=str(values.get("bus", "sata")),
        )
    if operation == "cdrom_mount":
        volume = _resource_base(request, detail.host.id, values, "volume")
        return await run_in_threadpool(
            state.vm_cdrom_change_service.preview_mount,
            base,
            volume,
            target=str(values.get("target", "")),
            bus=str(values.get("bus", "")),
            expected_source=_optional(values, "expected_source"),
            live=bool(values.get("live")),
        )
    if operation == "cdrom_eject":
        return await run_in_threadpool(
            state.vm_cdrom_change_service.preview_eject,
            base,
            target=str(values.get("target", "")),
            bus=str(values.get("bus", "")),
            expected_source=str(values.get("expected_source", "")),
            live=bool(values.get("live")),
        )
    if operation == "advanced_devices":
        return await run_in_threadpool(
            state.vm_advanced_device_change_service.preview_devices,
            base,
            _advanced_device_change(_form(detail, values)),
        )
    if operation == "numa":
        return await run_in_threadpool(
            state.vm_numa_change_service.preview_numa,
            base,
            _numa_change(_form(detail, values)),
        )
    if operation == "cputune":
        return await run_in_threadpool(
            state.vm_cputune_change_service.preview_cputune,
            base,
            _cputune_change(_form(detail, values)),
        )
    if operation in {"host_device", "shared_directory"}:
        return await _peripheral_preview(request, detail, operation, values)
    if operation in {
        "platform_iso_mount",
        "platform_iso_eject",
        "cached_iso_mount",
        "cached_iso_eject",
    }:
        return await _media_preview(request, detail, operation, values)
    raise ValueError("unsupported VM configuration operation")


async def _media_preview(
    request: Request, detail: VmDetail, operation: str, values: dict[str, Any]
) -> Any:
    platform = operation.startswith("platform_iso")
    eject = operation.endswith("_eject")
    service = (
        request.app.state.vm_platform_iso_service
        if platform
        else request.app.state.vm_cached_iso_service
    )
    if eject:
        method = service.preview_platform_eject if platform else service.preview_cached_eject
        return await run_in_threadpool(
            method,
            _base(detail),
            target=str(values.get("target", "")),
            bus=str(values.get("bus", "")),
            expected_source=str(values.get("expected_source", "")),
        )
    method = service.preview_platform_mount if platform else service.preview_cached_mount
    return await run_in_threadpool(
        method,
        _base(detail),
        str(values.get("media_item_id", "")),
        target=str(values.get("target", "")),
        bus=str(values.get("bus", "")),
        expected_source=_optional(values, "expected_source"),
    )


async def _peripheral_preview(
    request: Request,
    detail: VmDetail,
    operation: str,
    values: dict[str, Any],
) -> Any:
    service = request.app.state.vm_peripheral_change_service
    attach = str(values.get("action", "attach")) == "attach"
    if operation == "shared_directory":
        return await run_in_threadpool(
            service.preview_shared_directory,
            _base(detail),
            root_index=int(values.get("root_index", -1)),
            target_tag=str(values.get("target_tag", "")),
            driver=str(values.get("driver", "virtiofs")),
            readonly=bool(values.get("readonly")),
            attach=attach,
        )
    with request.app.state.database.session() as session:
        device = session.get(ResourceIndex, str(values.get("device_resource_id", "")))
    if device is None or device.persistent_hash is None or device.host_id != detail.host.id:
        raise ValueError("host device is unavailable")
    device_base = ResourceBaseVersion(
        device.id,
        detail.host.id,
        ResourceType(device.resource_type),
        device.native_id,
        device.observed_generation,
        device.persistent_hash,
        device.live_hash,
    )
    return await run_in_threadpool(
        service.preview_host_device,
        _base(detail),
        device_base,
        attach=attach,
    )


def _task_settings(request: Request, change_type: str) -> tuple[Any, str, str, str, int] | None:
    state = request.app.state
    values = {
        "cpu_topology": (state.vm_cpu_change_service, "vm.cpu_change", "更新 CPU", "cpu", 3),
        "memory_config": (
            state.vm_memory_change_service,
            "vm.memory_change",
            "更新内存",
            "memory",
            3,
        ),
        "disk_attach": (state.vm_disk_change_service, "vm.disk_change", "挂载磁盘", "disk", 3),
        "disk_detach": (state.vm_disk_change_service, "vm.disk_change", "移除磁盘设备", "disk", 3),
        "interface_attach": (
            state.vm_network_change_service,
            "vm.network_change",
            "添加网卡",
            "network",
            3,
        ),
        "interface_detach": (
            state.vm_network_change_service,
            "vm.network_change",
            "移除网卡",
            "network",
            3,
        ),
        "interface_update": (
            state.vm_network_change_service,
            "vm.network_change",
            "更新网卡",
            "network",
            3,
        ),
        "cdrom_mount": (
            state.vm_cdrom_change_service,
            "vm.cdrom_change",
            "挂载本地 ISO",
            "cdrom",
            3,
        ),
        "cdrom_eject": (state.vm_cdrom_change_service, "vm.cdrom_change", "弹出 ISO", "cdrom", 3),
        "cdrom_add": (
            state.vm_cdrom_change_service,
            "vm.cdrom_change",
            "添加光驱设备",
            "cdrom",
            3,
        ),
        "cdrom_platform_mount": (
            state.vm_platform_iso_service,
            "vm.platform_iso_change",
            "挂载平台 ISO",
            "platform-iso",
            3,
        ),
        "cdrom_platform_eject": (
            state.vm_platform_iso_service,
            "vm.platform_iso_change",
            "弹出平台 ISO",
            "platform-iso",
            3,
        ),
        "cdrom_cache_mount": (
            state.vm_cached_iso_service,
            "vm.cached_iso_change",
            "缓存并挂载平台 ISO",
            "cached-iso",
            8,
        ),
        "cdrom_cache_eject": (
            state.vm_cached_iso_service,
            "vm.cached_iso_change",
            "弹出缓存平台 ISO",
            "cached-iso",
            3,
        ),
        "advanced_devices": (
            state.vm_advanced_device_change_service,
            "vm.advanced_change",
            "更新高级设备",
            "advanced",
            3,
        ),
        "numa_config": (
            state.vm_numa_change_service,
            "vm.advanced_change",
            "更新 NUMA",
            "advanced",
            3,
        ),
        "cputune_config": (
            state.vm_cputune_change_service,
            "vm.advanced_change",
            "更新 CPU Pinning",
            "advanced",
            3,
        ),
    }
    peripheral = {
        "host_device_attach",
        "host_device_detach",
        "shared_directory_attach",
        "shared_directory_detach",
    }
    if change_type in peripheral:
        return (
            state.vm_peripheral_change_service,
            "vm.advanced_change",
            "更新 VM 外设",
            "advanced",
            3,
        )
    return values.get(change_type)


def _detail(request: Request, host_id: str, domain_uuid: str) -> VmDetail | None:
    try:
        return VmReadService(request.app.state.database).detail(host_id, domain_uuid)
    except ValueError:
        return None


def _base(detail: VmDetail) -> ResourceBaseVersion:
    if detail.resource.persistent_hash is None:
        raise ValueError("configuration requires a persistent VM")
    return ResourceBaseVersion(
        detail.resource.id,
        detail.host.id,
        ResourceType.VIRTUAL_MACHINE,
        detail.resource.native_id,
        detail.resource.observed_generation,
        detail.resource.persistent_hash,
        None,
    )


def _resource_base(
    request: Request,
    host_id: str,
    values: dict[str, Any],
    prefix: str,
) -> ResourceBaseVersion:
    resource_id = str(values.get(f"{prefix}_resource_id", ""))
    with request.app.state.database.session() as session:
        resource = session.get(ResourceIndex, resource_id)
    if (
        resource is None
        or resource.host_id != host_id
        or resource.resource_type != ResourceType.STORAGE_VOLUME
        or resource.persistent_hash is None
    ):
        raise ValueError("storage volume is unavailable")
    return ResourceBaseVersion(
        resource.id,
        host_id,
        ResourceType.STORAGE_VOLUME,
        resource.native_id,
        resource.observed_generation,
        resource.persistent_hash,
        None,
    )


def _form(detail: VmDetail, values: dict[str, Any]) -> FormData:
    pairs: list[tuple[str, str]] = [
        ("resource_id", detail.resource.id),
        ("generation", str(detail.resource.observed_generation)),
        ("persistent_hash", detail.resource.persistent_hash or ""),
    ]
    for key, value in values.items():
        if value is True:
            pairs.append((key, "on"))
        elif value not in (False, None, ""):
            pairs.append((key, str(value)))
    return FormData(dict(pairs))


def _optional(values: dict[str, Any], key: str) -> str | None:
    value = str(values.get(key, "")).strip()
    return value or None


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)


def _task_response(task_id: str, status_code: int) -> JSONResponse:
    payload = TaskCreatedResponse(task_id=task_id, location=f"/tasks/{task_id}")
    return no_store(JSONResponse(payload.model_dump(), status_code=status_code))
