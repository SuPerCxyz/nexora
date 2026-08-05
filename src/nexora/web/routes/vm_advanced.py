"""NUMA and CPUTune preview and confirmed task submission."""

from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData
from starlette.responses import Response

from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteConflict
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.read_service import TaskReadService
from nexora.vms.contracts import VmChangeTaskInput
from nexora.vms.cpu_changes import VmChangeError
from nexora.web.rendering import templates
from nexora.web.routes.vm_cpu import _base_version, _detail, _identity, _valid_csrf
from nexora.web.security import CSRF_COOKIE
from nexora.xml import (
    AdvancedDeviceChange,
    CpuTuneChange,
    EmulatorPinChange,
    NumaCellChange,
    NumaChange,
    VcpuPinChange,
)

router = APIRouter(include_in_schema=False)


@router.post("/hosts/{host_id}/vms/{domain_uuid}/numa/preview")
async def numa_change_preview(request: Request, host_id: str, domain_uuid: str) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return PlainTextResponse("Virtual machine not found", status_code=404)
    try:
        change = _numa_change(form)
        service = request.app.state.vm_numa_change_service
        preview = await run_in_threadpool(
            service.preview_numa,
            _base_version(detail, form),
            change,
        )
    except (TypeError, ValueError, ResourceWriteConflict, VmChangeError) as exc:
        return PlainTextResponse(str(exc), status_code=422)
    return templates.TemplateResponse(
        request=request,
        name="vms/advanced_preview.html",
        context={
            "administrator": identity,
            "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
            "vm": detail,
            "preview": preview,
            "change_type": "numa_config",
            "title": "NUMA 配置变更",
        },
    )


@router.post("/hosts/{host_id}/vms/{domain_uuid}/numa/apply")
async def numa_change_apply(request: Request, host_id: str, domain_uuid: str) -> Response:
    return await _apply(request, host_id, domain_uuid, "numa_config", "更新 NUMA")


@router.post("/hosts/{host_id}/vms/{domain_uuid}/cputune/preview")
async def cputune_change_preview(request: Request, host_id: str, domain_uuid: str) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return PlainTextResponse("Virtual machine not found", status_code=404)
    try:
        change = _cputune_change(form)
        service = request.app.state.vm_cputune_change_service
        preview = await run_in_threadpool(
            service.preview_cputune,
            _base_version(detail, form),
            change,
        )
    except (TypeError, ValueError, ResourceWriteConflict, VmChangeError) as exc:
        return PlainTextResponse(str(exc), status_code=422)
    return templates.TemplateResponse(
        request=request,
        name="vms/advanced_preview.html",
        context={
            "administrator": identity,
            "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
            "vm": detail,
            "preview": preview,
            "change_type": "cputune_config",
            "title": "CPU Pinning 配置变更",
        },
    )


@router.post("/hosts/{host_id}/vms/{domain_uuid}/cputune/apply")
async def cputune_change_apply(request: Request, host_id: str, domain_uuid: str) -> Response:
    return await _apply(request, host_id, domain_uuid, "cputune_config", "更新 CPU Pinning")


@router.post("/hosts/{host_id}/vms/{domain_uuid}/advanced-devices/preview")
async def advanced_devices_preview(
    request: Request,
    host_id: str,
    domain_uuid: str,
) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return PlainTextResponse("Virtual machine not found", status_code=404)
    try:
        service = request.app.state.vm_advanced_device_change_service
        preview = await run_in_threadpool(
            service.preview_devices,
            _base_version(detail, form),
            _advanced_device_change(form),
        )
    except (TypeError, ValueError, ResourceWriteConflict, VmChangeError) as exc:
        return PlainTextResponse(str(exc), status_code=422)
    return templates.TemplateResponse(
        request=request,
        name="vms/advanced_preview.html",
        context={
            "administrator": identity,
            "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
            "vm": detail,
            "preview": preview,
            "change_type": "advanced_devices",
            "action_path": "advanced-devices",
            "title": "高级设备配置变更",
        },
    )


@router.post("/hosts/{host_id}/vms/{domain_uuid}/advanced-devices/apply")
async def advanced_devices_apply(
    request: Request,
    host_id: str,
    domain_uuid: str,
) -> Response:
    return await _apply(request, host_id, domain_uuid, "advanced_devices", "更新高级设备")


@router.post("/hosts/{host_id}/vms/{domain_uuid}/host-device/preview")
async def host_device_preview(request: Request, host_id: str, domain_uuid: str) -> Response:
    return await _peripheral_preview(request, host_id, domain_uuid, "host_device")


@router.post("/hosts/{host_id}/vms/{domain_uuid}/shared-directory/preview")
async def shared_directory_preview(request: Request, host_id: str, domain_uuid: str) -> Response:
    return await _peripheral_preview(request, host_id, domain_uuid, "shared_directory")


@router.post("/hosts/{host_id}/vms/{domain_uuid}/peripheral/apply")
async def peripheral_apply(request: Request, host_id: str, domain_uuid: str) -> Response:
    form = await request.form()
    change_type = str(form.get("change_type", ""))
    if change_type not in {
        "host_device_attach",
        "host_device_detach",
        "shared_directory_attach",
        "shared_directory_detach",
    }:
        return PlainTextResponse("Peripheral change type is invalid", status_code=422)
    return await _apply(request, host_id, domain_uuid, change_type, "更新 VM 外设", form=form)


async def _apply(
    request: Request,
    host_id: str,
    domain_uuid: str,
    change_type: str,
    title_prefix: str,
    form: FormData | None = None,
) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = form or await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return PlainTextResponse("Virtual machine not found", status_code=404)
    active = TaskReadService(request.app.state.database).find_active_vm_write(
        host_id,
        detail.resource.native_id,
    )
    if active is not None:
        return RedirectResponse(f"/tasks/{active.id}", status_code=status.HTTP_303_SEE_OTHER)
    services = {
        "numa_config": request.app.state.vm_numa_change_service,
        "cputune_config": request.app.state.vm_cputune_change_service,
        "advanced_devices": request.app.state.vm_advanced_device_change_service,
        "host_device_attach": request.app.state.vm_peripheral_change_service,
        "host_device_detach": request.app.state.vm_peripheral_change_service,
        "shared_directory_attach": request.app.state.vm_peripheral_change_service,
        "shared_directory_detach": request.app.state.vm_peripheral_change_service,
    }
    service = services[change_type]
    try:
        plan = await run_in_threadpool(
            service.confirm,
            str(form.get("plan_id", "")),
            str(form.get("confirmation_token", "")),
            host_id=host_id,
            vm_uuid=detail.resource.native_id,
            change_type=change_type,
        )
    except VmChangeError as exc:
        return PlainTextResponse(str(exc), status_code=409)
    task_input = VmChangeTaskInput(
        plan.id,
        host_id,
        detail.resource.native_id,
        change_type,
    )
    task = request.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.advanced_change",
            title=f"{title_prefix} · {detail.resource.display_name}",
            idempotency_scope=f"vm:{host_id}:{detail.resource.native_id}:advanced",
            idempotency_key=plan.id,
            host_id=host_id,
            vm_uuid=detail.resource.native_id,
            resource_type=ResourceType.VIRTUAL_MACHINE,
            resource_id=detail.resource.id,
            total_steps=3,
            resumable=False,
            recovery_strategy="verify_only",
            input_summary=task_input.encode(),
        )
    )
    return RedirectResponse(f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


def _numa_change(form: FormData) -> NumaChange:
    cells: list[NumaCellChange] = []
    index = 0
    while True:
        prefix = f"cell_{index}_"
        cpus = str(form.get(prefix + "cpus", ""))
        if not cpus:
            break
        cell_id = int(str(form.get(prefix + "id", str(index))))
        memory_kib = int(str(form.get(prefix + "memory_kib", "0")))
        if memory_kib < 1:
            raise ValueError(f"cell {index} memory must be positive")
        mem_access = str(form.get(prefix + "mem_access", "")).strip() or None
        cells.append(NumaCellChange(cell_id, cpus, memory_kib, mem_access))
        index += 1
    return NumaChange(cells=cells)


def _cputune_change(form: FormData) -> CpuTuneChange:
    vcpu_pins: list[VcpuPinChange] = []
    index = 0
    while True:
        prefix = f"pin_{index}_"
        cpuset = str(form.get(prefix + "cpuset", ""))
        if not cpuset:
            break
        vcpu_id = int(str(form.get(prefix + "vcpu", str(index))))
        vcpu_pins.append(VcpuPinChange(vcpu_id, cpuset))
        index += 1
    emulator_cpuset = str(form.get("emulator_cpuset", "")).strip() or None
    emulator_pin = EmulatorPinChange(emulator_cpuset) if emulator_cpuset else None
    return CpuTuneChange(vcpu_pins=vcpu_pins, emulator_pin=emulator_pin)


def _advanced_device_change(form: FormData) -> AdvancedDeviceChange:
    watchdog_enabled = str(form.get("watchdog_enabled", "")) == "on"
    vsock_mode = str(form.get("vsock_mode", "remove"))
    cid_value = str(form.get("vsock_cid", "")).strip()
    bits_value = str(form.get("maxphysaddr_bits", "")).strip()
    return AdvancedDeviceChange(
        watchdog_model=str(form.get("watchdog_model", "i6300esb")) if watchdog_enabled else None,
        watchdog_action=str(form.get("watchdog_action", "reset")) if watchdog_enabled else None,
        vsock_mode=vsock_mode,
        vsock_cid=int(cid_value) if cid_value else None,
        cache_mode=str(form.get("cache_mode", "")).strip() or None,
        maxphysaddr_mode=str(form.get("maxphysaddr_mode", "")).strip() or None,
        maxphysaddr_bits=int(bits_value) if bits_value else None,
    )


async def _peripheral_preview(
    request: Request,
    host_id: str,
    domain_uuid: str,
    kind: str,
) -> Response:
    identity = _identity(request)
    if identity is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not _valid_csrf(request, form.get("csrf_token")):
        return PlainTextResponse("CSRF validation failed", status_code=403)
    detail = _detail(request, host_id, domain_uuid)
    if detail is None:
        return PlainTextResponse("Virtual machine not found", status_code=404)
    service = request.app.state.vm_peripheral_change_service
    try:
        attach = str(form.get("action", "attach")) == "attach"
        if kind == "host_device":
            device_id = str(form.get("device_resource_id", ""))
            with request.app.state.database.session() as session:
                device = session.get(ResourceIndex, device_id)
            if device is None or device.persistent_hash is None:
                raise ValueError("host device is unavailable")
            device_base = ResourceBaseVersion(
                device.id,
                host_id,
                ResourceType(device.resource_type),
                device.native_id,
                device.observed_generation,
                device.persistent_hash,
                device.live_hash,
            )
            preview = await run_in_threadpool(
                service.preview_host_device,
                _base_version(detail, form),
                device_base,
                attach=attach,
            )
        else:
            preview = await run_in_threadpool(
                service.preview_shared_directory,
                _base_version(detail, form),
                root_index=int(str(form.get("root_index", "-1"))),
                target_tag=str(form.get("target_tag", "")),
                driver=str(form.get("driver", "virtiofs")),
                readonly=str(form.get("readonly", "")) == "on",
                attach=attach,
            )
    except (TypeError, ValueError, ResourceWriteConflict, VmChangeError) as exc:
        return PlainTextResponse(str(exc), status_code=422)
    return templates.TemplateResponse(
        request=request,
        name="vms/advanced_preview.html",
        context={
            "administrator": identity,
            "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
            "vm": detail,
            "preview": preview,
            "change_type": preview.plan.change_type,
            "action_path": "peripheral",
            "title": "VM 外设配置变更",
        },
    )
