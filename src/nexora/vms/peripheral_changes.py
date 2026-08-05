"""Authority checks and persistent XML plans for VM peripherals."""

import json
from dataclasses import asdict
from pathlib import PurePosixPath

from sqlalchemy import select

from nexora.db import Database
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import RemoteExecutor
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.contracts import ResourceObservation
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.node_device_discovery import NodeDeviceDiscoveryService
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlan, VmChangePlanStatus
from nexora.vms.cpu_changes import (
    ChangeProgress,
    VmChangeConflict,
    VmChangePreview,
    VmCpuChangeService,
)
from nexora.xml import (
    HostDeviceChange,
    LibvirtXmlDocument,
    SharedDirectoryChange,
    apply_host_device_attach,
    apply_host_device_detach,
    apply_shared_directory_attach,
    apply_shared_directory_detach,
    verify_shared_directory_attach_result,
)


class VmPeripheralChangeService(VmCpuChangeService):
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        discovery: DomainDiscoveryService,
        store: ResourceIndexStore,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
        device_discovery: NodeDeviceDiscoveryService,
        roots: tuple[str, ...],
    ) -> None:
        super().__init__(database, executor, discovery, store, guard, locks)
        self.device_discovery = device_discovery
        self.roots = roots

    def _verified_after_hash(
        self,
        plan: VmChangePlan,
        observation: ResourceObservation,
    ) -> str:
        if plan.change_type != "shared_directory_attach":
            return super()._verified_after_hash(plan, observation)
        content = observation.documents.get("persistent_xml")
        if content is None or observation.persistent_hash is None:
            raise VmChangeConflict("authoritative persistent VM XML is unavailable")
        payload = json.loads(plan.change_input_json)
        change = SharedDirectoryChange(
            source_path=str(payload.get("source_path", "")),
            target_tag=str(payload.get("target_tag", "")),
            driver=str(payload.get("driver", "")),
            readonly=bool(payload.get("readonly", False)),
        )
        document = LibvirtXmlDocument.parse(content, expected_root="domain")
        try:
            verify_shared_directory_attach_result(
                document,
                change,
                original_hash=plan.base_persistent_hash,
            )
        except ValueError as exc:
            raise VmChangeConflict(str(exc)) from exc
        return observation.persistent_hash

    def preview_host_device(
        self,
        vm_base: ResourceBaseVersion,
        device_base: ResourceBaseVersion,
        *,
        attach: bool,
    ) -> VmChangePreview:
        self._require_shutoff(vm_base)
        self.device_discovery.run(vm_base.host_id)
        device = self._device(vm_base, device_base)
        change = _device_change(device)
        if attach:
            self._require_unreferenced(vm_base.host_id, change.identity)
        current, original_xml, original_hash = self._current_persistent(vm_base)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        if attach:
            apply_host_device_attach(proposed, change)
        else:
            apply_host_device_detach(proposed, change)
        return self._create_preview(
            vm_base,
            "host_device_attach" if attach else "host_device_detach",
            {**asdict(change), "device_resource_id": device.id},
            current,
            proposed,
            original_xml,
            original_hash,
        )

    def execute(
        self,
        plan_id: str,
        *,
        task_id: str,
        expected_change_type: str | None = None,
        progress: ChangeProgress | None = None,
    ) -> str:
        plan = self.plan_store.load(plan_id, VmChangePlanStatus.CONFIRMED)
        payload = json.loads(plan.change_input_json)
        if plan.change_type.startswith("host_device_"):
            device_id = str(payload.get("device_resource_id", ""))
            with self.database.session() as session:
                device = session.get(ResourceIndex, device_id)
            if device is None:
                raise VmChangeConflict("host device disappeared after confirmation")
            if device.host_id != plan.host_id or device.resource_type not in {
                ResourceType.PCI_DEVICE,
                ResourceType.USB_DEVICE,
            }:
                raise VmChangeConflict("host device is outside the VM scope")
            device_type = ResourceType(device.resource_type)
            device_native_id = device.native_id
            self.locks.acquire(
                plan.host_id,
                device_type,
                device_native_id,
                task_id,
            )
            try:
                self.device_discovery.run(plan.host_id)
                with self.database.session() as session:
                    device = session.get(ResourceIndex, device_id)
                    if device is None:
                        raise VmChangeConflict("host device disappeared after confirmation")
                    self._validate_device(device)
                    current_identity = _device_change(device).identity
                if tuple(str(value) for value in payload.get("identity", ())) != current_identity:
                    raise VmChangeConflict("host device identity changed after confirmation")
                if plan.change_type == "host_device_attach":
                    self._require_unreferenced(
                        plan.host_id,
                        current_identity,
                    )
                return super().execute(
                    plan_id,
                    task_id=task_id,
                    expected_change_type=expected_change_type,
                    progress=progress,
                )
            finally:
                self.locks.release(
                    plan.host_id,
                    device_type,
                    device_native_id,
                    task_id,
                )
        root_index = int(payload.get("root_index", -1))
        if root_index < 0:
            raise VmChangeConflict("shared directory authorization changed")
        try:
            configured = self.roots[root_index]
        except IndexError as exc:
            raise VmChangeConflict("shared directory authorization changed") from exc
        if self._realpath(plan.host_id, configured) != str(payload.get("source_path", "")):
            raise VmChangeConflict("shared directory changed after confirmation")
        return super().execute(
            plan_id,
            task_id=task_id,
            expected_change_type=expected_change_type,
            progress=progress,
        )

    def preview_shared_directory(
        self,
        vm_base: ResourceBaseVersion,
        *,
        root_index: int,
        target_tag: str,
        driver: str,
        readonly: bool,
        attach: bool,
    ) -> VmChangePreview:
        self._require_shutoff(vm_base)
        if root_index < 0:
            raise VmChangeConflict("shared directory root is not authorized")
        try:
            configured = self.roots[root_index]
        except IndexError as exc:
            raise VmChangeConflict("shared directory root is not authorized") from exc
        path = self._realpath(vm_base.host_id, configured)
        if path != configured.rstrip("/") or PurePosixPath(path) != PurePosixPath(configured):
            raise VmChangeConflict("shared directory realpath differs from the configured root")
        change = SharedDirectoryChange(path, target_tag, driver, readonly)
        current, original_xml, original_hash = self._current_persistent(vm_base)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        if attach:
            apply_shared_directory_attach(proposed, change)
        else:
            apply_shared_directory_detach(proposed, change)
        return self._create_preview(
            vm_base,
            "shared_directory_attach" if attach else "shared_directory_detach",
            {**asdict(change), "root_index": root_index},
            current,
            proposed,
            original_xml,
            original_hash,
        )

    def _device(self, vm_base: ResourceBaseVersion, base: ResourceBaseVersion) -> ResourceIndex:
        if base.host_id != vm_base.host_id or base.resource_type not in {
            ResourceType.PCI_DEVICE,
            ResourceType.USB_DEVICE,
        }:
            raise VmChangeConflict("host device is outside the VM scope")
        self.guard.verify(base)
        with self.database.session() as session:
            device = session.get(ResourceIndex, base.resource_id)
            if device is None or device.status == ResourceStatus.MISSING:
                raise VmChangeConflict("host device is unavailable")
            self._validate_device(device)
            return device

    def _validate_device(self, device: ResourceIndex) -> None:
        if device.status == ResourceStatus.MISSING:
            raise VmChangeConflict("host device is unavailable")
        details = json.loads(device.details_json)
        if device.resource_type == ResourceType.PCI_DEVICE:
            if not details.get("iommu_group"):
                raise VmChangeConflict("PCI device has no IOMMU group")
            if details.get("driver") != "vfio-pci":
                raise VmChangeConflict("PCI device is not pre-bound to vfio-pci")

    def _require_shutoff(self, base: ResourceBaseVersion) -> None:
        with self.database.session() as session:
            vm = session.get(ResourceIndex, base.resource_id)
            details = json.loads(vm.details_json) if vm is not None else {}
            if details.get("state") not in {"shut off", "shut_off", "shutoff"}:
                raise VmChangeConflict("peripheral changes require a shutoff VM")

    def _require_unreferenced(self, host_id: str, identity: tuple[str, ...]) -> None:
        with self.database.session() as session:
            vms = session.scalars(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                )
            )
            for vm in vms:
                details = json.loads(vm.details_json)
                for item in details.get("host_devices", []):
                    address = item.get("address") if isinstance(item, dict) else None
                    if isinstance(address, dict) and _parsed_identity(item, address) == identity:
                        raise VmChangeConflict(
                            f"host device is already referenced by {vm.display_name}"
                        )

    def _realpath(self, host_id: str, path: str) -> str:
        result = self.executor.run(
            host_id,
            CommandSpec("realpath", ("-e", "--", path)),
            timeout=10,
            env={"LC_ALL": "C"},
        )
        if result.exit_code or result.timed_out or result.stdout_truncated:
            raise VmChangeConflict("shared directory is unavailable")
        try:
            value = result.stdout.decode().strip()
        except UnicodeDecodeError as exc:
            raise VmChangeConflict("shared directory realpath is invalid") from exc
        if not value.startswith("/") or len(value) > 4096:
            raise VmChangeConflict("shared directory realpath is invalid")
        return value


def _device_change(device: ResourceIndex) -> HostDeviceChange:
    if device.resource_type == ResourceType.PCI_DEVICE:
        domain, bus_slot = device.native_id.split(":", 1)
        bus, slot_function = bus_slot.split(":", 1)
        slot, function = slot_function.split(".", 1)
        return HostDeviceChange(
            "pci",
            (f"0x{domain}", f"0x{bus}", f"0x{slot}", f"0x{function}"),
        )
    bus, number, _vendor, _product = json.loads(device.native_id)
    return HostDeviceChange("usb", (str(bus), str(number)))


def _parsed_identity(item: dict[str, object], address: dict[str, object]) -> tuple[str, ...] | None:
    device_type = item.get("type")
    if device_type == "pci":
        return tuple(str(address.get(name, "")) for name in ("domain", "bus", "slot", "function"))
    if device_type == "usb":
        return tuple(str(address.get(name, "")) for name in ("bus", "device"))
    return None
