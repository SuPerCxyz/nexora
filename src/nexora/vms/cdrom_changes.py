"""Persistent local ISO mount and eject plans for existing CD-ROM devices."""

import json
from dataclasses import asdict

from sqlalchemy import select

from nexora.db import Database
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlan, VmChangePlanStatus
from nexora.vms.cpu_changes import (
    ChangeProgress,
    VmChangeConflict,
    VmChangePreview,
    VmCpuChangeService,
    _uses_sudo,
)
from nexora.xml import (
    CdromMediaChange,
    LibvirtXmlDocument,
    apply_cdrom_add,
    apply_cdrom_media,
)


class VmCdromChangeService(VmCpuChangeService):
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
        self._cached_plan: VmChangePlan | None = None

    def preview_add(
        self,
        vm_base: ResourceBaseVersion,
        *,
        bus: str,
    ) -> VmChangePreview:
        current, original_xml, original_hash = self._current_persistent(vm_base)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_cdrom_add(proposed, bus)
        return self._create_preview(
            vm_base,
            "cdrom_add",
            {"bus": bus},
            current,
            proposed,
            original_xml,
            original_hash,
        )

    def preview_mount(
        self,
        vm_base: ResourceBaseVersion,
        volume_base: ResourceBaseVersion,
        *,
        target: str,
        bus: str,
        expected_source: str | None,
        live: bool = False,
    ) -> VmChangePreview:
        self.discovery.run(vm_base.host_id)
        self.storage_discovery.run(vm_base.host_id)
        current, original_xml, original_hash = self._current_persistent(vm_base)
        volume, path = self._verified_iso(vm_base, volume_base)
        change = CdromMediaChange(target, bus, expected_source, path)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_cdrom_media(proposed, change)
        change_input = {
            **asdict(change),
            "volume_resource_id": volume.id,
            "volume_native_id": volume.native_id,
            "volume_generation": volume.observed_generation,
            "volume_hash": volume.persistent_hash,
            "live": live,
        }
        return self._create_preview(
            vm_base,
            "cdrom_mount",
            change_input,
            current,
            proposed,
            original_xml,
            original_hash,
        )

    def preview_eject(
        self,
        vm_base: ResourceBaseVersion,
        *,
        target: str,
        bus: str,
        expected_source: str,
        live: bool = False,
    ) -> VmChangePreview:
        current, original_xml, original_hash = self._current_persistent(vm_base)
        change = CdromMediaChange(target, bus, expected_source, None)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_cdrom_media(proposed, change)
        return self._create_preview(
            vm_base,
            "cdrom_eject",
            {**asdict(change), "live": live},
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
        if plan.change_type != "cdrom_mount":
            return super().execute(
                plan_id,
                task_id=task_id,
                expected_change_type=expected_change_type,
                progress=progress,
            )
        volume_base = _volume_base(plan.change_input_json, plan.host_id)
        self.locks.acquire(
            plan.host_id,
            ResourceType.STORAGE_VOLUME,
            volume_base.native_id,
            task_id,
        )
        try:
            self.discovery.run(plan.host_id)
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
            self._verified_iso(vm_base, volume_base)
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

    def _define(self, host_id: str, content: bytes) -> CommandResult:
        payload = _change_input(self._current_plan.change_input_json)
        if not bool(payload.get("live", False)):
            return super()._define(host_id, content)
        return self._apply_live_media(host_id, payload)

    def _apply_live_media(
        self,
        host_id: str,
        payload: dict[str, object],
    ) -> CommandResult:
        host = self._host(host_id)
        change_type = self._current_plan.change_type
        target = str(payload.get("target", ""))
        new_source = payload.get("new_source")
        args: tuple[str, ...]
        if change_type == "cdrom_eject":
            args = (
                "-c",
                host.libvirt_uri,
                "change-media",
                self._current_plan.vm_uuid,
                target,
                "--eject",
                "--live",
                "--persistent",
            )
            stdin: bytes = b""
        else:
            if not isinstance(new_source, str) or not new_source.startswith("/"):
                raise VmChangeConflict("live CD-ROM mount requires a local source path")
            args = (
                "-c",
                host.libvirt_uri,
                "change-media",
                self._current_plan.vm_uuid,
                target,
                new_source,
                "--insert",
                "--live",
                "--persistent",
            )
            stdin = b""
        return self.executor.run(
            host_id,
            CommandSpec("virsh", args),
            sudo=_uses_sudo(host),
            timeout=60,
            stdin=stdin,
            env={"LC_ALL": "C"},
            sensitive=True,
        )

    @property
    def _current_plan(self) -> VmChangePlan:
        if self._cached_plan is None:
            raise VmChangeConflict("no active CD-ROM change plan")
        return self._cached_plan

    @_current_plan.setter
    def _current_plan(self, value: VmChangePlan) -> None:
        self._cached_plan = value

    def _verified_iso(
        self,
        vm_base: ResourceBaseVersion,
        volume_base: ResourceBaseVersion,
    ) -> tuple[ResourceIndex, str]:
        if (
            volume_base.host_id != vm_base.host_id
            or volume_base.resource_type != ResourceType.STORAGE_VOLUME
        ):
            raise VmChangeConflict("ISO volume is outside the VM host scope")
        self.guard.verify(volume_base)
        with self.database.session() as session:
            volume = session.get(ResourceIndex, volume_base.resource_id)
            if (
                volume is None
                or volume.status != ResourceStatus.MANAGED
                or volume.parent_native_id is None
            ):
                raise VmChangeConflict("ISO volume is not writable")
            pool = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == vm_base.host_id,
                    ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                    ResourceIndex.native_id == volume.parent_native_id,
                    ResourceIndex.status == ResourceStatus.MANAGED,
                )
            )
            details = json.loads(volume.details_json)
            pool_details = json.loads(pool.details_json) if pool is not None else {}
            path = details.get("path")
            if (
                pool is None
                or not bool(pool_details.get("active"))
                or details.get("format") != "raw"
                or not isinstance(path, str)
                or not path.startswith("/")
                or not path.lower().endswith(".iso")
                or not volume.display_name.lower().endswith(".iso")
            ):
                raise VmChangeConflict("storage volume is not an available local ISO")
            return volume, path


def _volume_base(value: str, host_id: str) -> ResourceBaseVersion:
    try:
        payload = json.loads(value)
        resource_id = str(payload["volume_resource_id"])
        native_id = str(payload["volume_native_id"])
        generation_value = payload["volume_generation"]
        if isinstance(generation_value, bool) or not isinstance(generation_value, (str, int)):
            raise ValueError
        generation = int(generation_value)
        persistent_hash = str(payload["volume_hash"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise VmChangeConflict("CD-ROM ISO volume base is invalid") from exc
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
        raise VmChangeConflict("CD-ROM change input is invalid") from exc
    if not isinstance(payload, dict):
        raise VmChangeConflict("CD-ROM change input is invalid")
    return payload
