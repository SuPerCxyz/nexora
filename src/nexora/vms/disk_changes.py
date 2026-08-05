"""Structured persistent VM disk attach and detach plans."""

import json
from dataclasses import asdict
from io import BytesIO

from lxml import etree
from sqlalchemy import select

from nexora.db import Database
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.contracts import ResourceObservation
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.storage.usage import StoragePoolUsageGuard
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlan, VmChangePlanStatus
from nexora.vms.cpu_changes import (
    ChangeProgress,
    VmChangeConflict,
    VmChangeError,
    VmChangePreview,
    VmCpuChangeService,
    _uses_sudo,
)
from nexora.xml import (
    DiskAttachChange,
    DiskDetachChange,
    LibvirtXmlDocument,
    apply_disk_attach,
    apply_disk_detach,
    verify_disk_attach_result,
)


class VmDiskChangeService(VmCpuChangeService):
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        discovery: DomainDiscoveryService,
        store: ResourceIndexStore,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
        storage_discovery: StorageDiscoveryService,
    ) -> None:
        super().__init__(database, executor, discovery, store, guard, locks)
        self.storage_discovery = storage_discovery
        self.usage = StoragePoolUsageGuard(self.database)
        self._cached_plan: VmChangePlan | None = None

    def preview_attach(
        self,
        vm_base: ResourceBaseVersion,
        volume_base: ResourceBaseVersion,
        *,
        bus: str,
        cache: str | None = None,
        io: str | None = None,
        discard: str | None = None,
        serial: str | None = None,
        readonly: bool = False,
        shareable: bool = False,
        live: bool = False,
    ) -> VmChangePreview:
        self._refresh_domains(vm_base.host_id)
        self.storage_discovery.run(vm_base.host_id)
        current, original_xml, original_hash = self._current_persistent(vm_base)
        volume, pool, details = self._verified_volume(vm_base, volume_base)
        references = self.usage.volume_references(
            vm_base.host_id,
            pool_name=pool.display_name,
            volume_name=volume.display_name,
            volume_key=str(details["key"]),
            volume_path=_optional_text(details.get("path")),
        )
        if references:
            raise VmChangeConflict(
                f"storage volume is already referenced by VM {references[0].vm_name}"
            )
        source_path = _required_path(details.get("path"))
        change = DiskAttachChange(
            source_path,
            str(details.get("format")),
            bus,
            cache=cache,
            io=io,
            discard=discard,
            serial=serial,
            readonly=readonly,
            shareable=shareable,
        )
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        target = apply_disk_attach(proposed, change)
        change_input = {
            **asdict(change),
            "target": target,
            "volume_resource_id": volume.id,
            "volume_native_id": volume.native_id,
            "volume_generation": volume.observed_generation,
            "volume_hash": volume.persistent_hash,
            "live": live,
        }
        return self._create_preview(
            vm_base,
            "disk_attach",
            change_input,
            current,
            proposed,
            original_xml,
            original_hash,
        )

    def preview_detach(
        self,
        vm_base: ResourceBaseVersion,
        change: DiskDetachChange,
        *,
        live: bool = False,
    ) -> VmChangePreview:
        current, original_xml, original_hash = self._current_persistent(vm_base)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_disk_detach(proposed, change)
        change_input = {**asdict(change), "live": live}
        return self._create_preview(
            vm_base,
            "disk_detach",
            change_input,
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
        self._cached_plan = plan
        if plan.change_type == "disk_attach":
            volume_base = _volume_base(plan.change_input_json, plan.host_id)
            self.locks.acquire(
                plan.host_id,
                ResourceType.STORAGE_VOLUME,
                volume_base.native_id,
                task_id,
            )
            try:
                self._refresh_domains(plan.host_id)
                self.storage_discovery.run(plan.host_id)
                vm_base = ResourceBaseVersion(
                    plan.resource_index_id,
                    plan.host_id,
                    ResourceType.VIRTUAL_MACHINE,
                    plan.vm_uuid,
                    plan.base_generation,
                    plan.base_persistent_hash,
                    None,
                )
                volume, pool, details = self._verified_volume(vm_base, volume_base)
                references = self.usage.volume_references(
                    plan.host_id,
                    pool_name=pool.display_name,
                    volume_name=volume.display_name,
                    volume_key=str(details["key"]),
                    volume_path=_optional_text(details.get("path")),
                )
                if references:
                    raise VmChangeConflict(
                        f"storage volume is already referenced by VM {references[0].vm_name}"
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
                    ResourceType.STORAGE_VOLUME,
                    volume_base.native_id,
                    task_id,
                )
        return super().execute(
            plan_id,
            task_id=task_id,
            expected_change_type=expected_change_type,
            progress=progress,
        )

    def _verified_volume(
        self,
        vm_base: ResourceBaseVersion,
        volume_base: ResourceBaseVersion,
    ) -> tuple[ResourceIndex, ResourceIndex, dict[str, object]]:
        if (
            volume_base.host_id != vm_base.host_id
            or volume_base.resource_type != ResourceType.STORAGE_VOLUME
        ):
            raise VmChangeConflict("storage volume is outside the VM host scope")
        self.guard.verify(volume_base)
        with self.database.session() as session:
            volume = session.get(ResourceIndex, volume_base.resource_id)
            if (
                volume is None
                or volume.status != ResourceStatus.MANAGED
                or volume.parent_native_id is None
            ):
                raise VmChangeConflict("storage volume is not writable")
            pool = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == vm_base.host_id,
                    ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                    ResourceIndex.native_id == volume.parent_native_id,
                    ResourceIndex.status == ResourceStatus.MANAGED,
                )
            )
            if pool is None:
                raise VmChangeConflict("storage volume pool is unavailable")
            details: dict[str, object] = json.loads(volume.details_json)
            pool_details = json.loads(pool.details_json)
            if (
                not bool(pool_details.get("active"))
                or details.get("format") not in {"qcow2", "raw"}
                or volume.display_name.lower().endswith(".iso")
                or details.get("key") is None
            ):
                raise VmChangeConflict("storage volume cannot be attached")
            return volume, pool, details

    def _verified_after_hash(
        self,
        plan: VmChangePlan,
        observation: ResourceObservation,
    ) -> str:
        if plan.change_type != "disk_attach":
            return super()._verified_after_hash(plan, observation)
        content = observation.documents.get("persistent_xml")
        if content is None or observation.persistent_hash is None:
            raise VmChangeConflict("authoritative persistent VM XML is unavailable")
        payload = _change_input(plan.change_input_json)
        change = DiskAttachChange(
            _required_path(payload.get("source_path")),
            str(payload.get("volume_format")),
            str(payload.get("bus")),
            cache=_optional_str(payload.get("cache")),
            io=_optional_str(payload.get("io")),
            discard=_optional_str(payload.get("discard")),
            serial=_optional_str(payload.get("serial")),
            readonly=bool(payload.get("readonly", False)),
            shareable=bool(payload.get("shareable", False)),
        )
        target = str(payload.get("target"))
        document = LibvirtXmlDocument.parse(content, expected_root="domain")
        try:
            verify_disk_attach_result(
                document,
                change,
                target=target,
                original_hash=plan.base_persistent_hash,
            )
        except ValueError as exc:
            raise VmChangeConflict(str(exc)) from exc
        return observation.persistent_hash

    def _refresh_domains(self, host_id: str) -> None:
        self.discovery.run(host_id)

    def _define(self, host_id: str, content: bytes) -> CommandResult:
        payload = _change_input(self._current_plan.change_input_json)
        if not bool(payload.get("live", False)):
            return super()._define(host_id, content)
        return self._apply_live_device(host_id, content, payload)

    def _apply_live_device(
        self,
        host_id: str,
        full_xml: bytes,
        payload: dict[str, object],
    ) -> CommandResult:
        host = self._host(host_id)
        change_type = self._current_plan.change_type
        device_xml = _extract_device_xml(full_xml, change_type, payload)
        if change_type == "disk_attach":
            args = (
                "-c",
                host.libvirt_uri,
                "attach-device",
                self._current_plan.vm_uuid,
                "/dev/stdin",
                "--live",
                "--persistent",
            )
        else:
            args = (
                "-c",
                host.libvirt_uri,
                "detach-device",
                self._current_plan.vm_uuid,
                "/dev/stdin",
                "--live",
                "--persistent",
            )
        return self.executor.run(
            host_id,
            CommandSpec("virsh", args),
            sudo=_uses_sudo(host),
            timeout=60,
            stdin=device_xml,
            env={"LC_ALL": "C"},
            sensitive=True,
        )

    @property
    def _current_plan(self) -> VmChangePlan:
        if self._cached_plan is None:
            raise VmChangeError("no active disk change plan")
        return self._cached_plan

    @_current_plan.setter
    def _current_plan(self, value: VmChangePlan) -> None:
        self._cached_plan = value


def _extract_device_xml(
    full_xml: bytes,
    change_type: str,
    payload: dict[str, object],
) -> bytes:
    """Extract the device XML snippet for virsh attach/detach-device."""
    tree = etree.parse(BytesIO(full_xml))
    root = tree.getroot()
    if change_type == "disk_attach":
        target = str(payload.get("target", ""))
        for disk in root.findall("./devices/disk"):
            t = disk.find("target")
            if t is not None and t.get("dev") == target:
                return etree.tostring(disk, encoding="UTF-8")
        raise VmChangeConflict("disk device not found in proposed XML")
    else:
        source = str(payload.get("source", ""))
        for disk in root.findall("./devices/disk"):
            src = disk.find("source")
            if src is not None and (src.get("file") == source or src.get("dev") == source):
                return etree.tostring(disk, encoding="UTF-8")
        raise VmChangeConflict("disk device not found in original XML")


def _required_path(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "\0" in value:
        raise VmChangeConflict("storage volume path is invalid")
    return value


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value


def _volume_base(value: str, host_id: str) -> ResourceBaseVersion:
    payload = _change_input(value)
    try:
        resource_id = str(payload["volume_resource_id"])
        native_id = str(payload["volume_native_id"])
        generation = _required_int(payload["volume_generation"])
        persistent_hash = str(payload["volume_hash"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VmChangeConflict("disk attach volume base is invalid") from exc
    if (
        not resource_id
        or not native_id
        or generation < 1
        or len(persistent_hash) != 64
        or any(character not in "0123456789abcdef" for character in persistent_hash)
    ):
        raise VmChangeConflict("disk attach volume base is invalid")
    return ResourceBaseVersion(
        resource_id,
        host_id,
        ResourceType.STORAGE_VOLUME,
        native_id,
        generation,
        persistent_hash,
        None,
    )


def _change_input(value: str) -> dict[str, object]:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise VmChangeConflict("disk attach change input is invalid") from exc
    if not isinstance(payload, dict):
        raise VmChangeConflict("disk attach change input is invalid")
    return payload


def _required_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("integer value is invalid")
    return int(value)
