"""Verified remote-cache fallback for platform ISO CD-ROM media."""

import json
from dataclasses import asdict

from sqlalchemy import select

from nexora.config import Settings
from nexora.db import Database
from nexora.hosts.models import SudoMode
from nexora.media.iso_cache import MediaIsoCache
from nexora.media.models import MediaItem, MediaKind, MediaStatus
from nexora.remote.executor import RemoteExecutor
from nexora.remote.transfer import RemoteFileTransfer
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.cdrom_changes import VmCdromChangeService
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.cpu_changes import ChangeProgress, VmChangeConflict, VmChangePreview
from nexora.xml import CdromMediaChange, LibvirtXmlDocument, apply_cdrom_media

CACHE_LOCK_TYPE = "media_cache"


class VmCachedIsoService(VmCdromChangeService):
    def __init__(
        self,
        settings: Settings,
        database: Database,
        executor: RemoteExecutor,
        transfer: RemoteFileTransfer,
        discovery: DomainDiscoveryService,
        store: ResourceIndexStore,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
        storage_discovery: StorageDiscoveryService,
    ) -> None:
        super().__init__(
            database,
            executor,
            discovery,
            store,
            guard,
            locks,
            storage_discovery,
        )
        self.cache = MediaIsoCache(settings.library_dir, executor, transfer)

    def preview_cached_mount(
        self,
        vm_base: ResourceBaseVersion,
        media_item_id: str,
        *,
        target: str,
        bus: str,
        expected_source: str | None,
    ) -> VmChangePreview:
        self._require_inactive(vm_base.host_id, vm_base.native_id)
        item = self._media_item(media_item_id)
        cache_path = self.cache.path_for(item.sha256)
        current, original_xml, original_hash = self._current_persistent(vm_base)
        change = CdromMediaChange(target, bus, expected_source, cache_path)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_cdrom_media(proposed, change)
        return self._create_preview(
            vm_base,
            "cdrom_cache_mount",
            {
                **asdict(change),
                "media_item_id": item.id,
                "media_sha256": item.sha256,
            },
            current,
            proposed,
            original_xml,
            original_hash,
        )

    def preview_cached_eject(
        self,
        vm_base: ResourceBaseVersion,
        *,
        target: str,
        bus: str,
        expected_source: str,
    ) -> VmChangePreview:
        self._require_inactive(vm_base.host_id, vm_base.native_id)
        self.cache.validate_path(expected_source)
        current, original_xml, original_hash = self._current_persistent(vm_base)
        change = CdromMediaChange(target, bus, expected_source, None)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_cdrom_media(proposed, change)
        return self._create_preview(
            vm_base,
            "cdrom_cache_eject",
            asdict(change),
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
        self._require_inactive(plan.host_id, plan.vm_uuid)
        payload = _payload(plan.change_input_json)
        key = "expected_source" if plan.change_type.endswith("eject") else "new_source"
        path = str(payload[key])
        self.cache.validate_path(path)
        self.locks.acquire(plan.host_id, CACHE_LOCK_TYPE, path, task_id)
        try:
            if plan.change_type == "cdrom_cache_mount":
                return self._execute_mount(
                    plan_id,
                    plan.host_id,
                    payload,
                    task_id,
                    expected_change_type,
                    progress,
                )
            result = super().execute(
                plan_id,
                task_id=task_id,
                expected_change_type=expected_change_type,
                progress=progress,
            )
            return self._cleanup_after_eject(plan.host_id, path, result)
        finally:
            self.locks.release(plan.host_id, CACHE_LOCK_TYPE, path, task_id)

    def _execute_mount(
        self,
        plan_id: str,
        host_id: str,
        payload: dict[str, object],
        task_id: str,
        expected_change_type: str | None,
        progress: ChangeProgress | None,
    ) -> str:
        item = self._media_item(str(payload["media_item_id"]))
        if item.sha256 != payload.get("media_sha256"):
            raise VmChangeConflict("platform ISO changed after preview")
        host = self._host(host_id)
        sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        cached = self.cache.ensure(
            host_id,
            item,
            task_id=task_id,
            sudo=sudo,
            progress=progress,
        )
        try:
            result = super().execute(
                plan_id,
                task_id=task_id,
                expected_change_type=expected_change_type,
                progress=_offset(progress, 5),
            )
        except Exception:
            if cached.created:
                self.cache.remove(host_id, cached.path, sudo=sudo)
            raise
        return f"{result}; cache={cached.path}; cache_created={str(cached.created).lower()}"

    def _cleanup_after_eject(self, host_id: str, path: str, result: str) -> str:
        self.discovery.run(host_id)
        if self._is_referenced(host_id, path):
            return f"{result}; cache retained because another VM references it"
        host = self._host(host_id)
        sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        try:
            self.cache.remove(host_id, path, sudo=sudo)
        except Exception:
            return f"{result}; cache cleanup requires manual intervention; path={path}"
        return f"{result}; cache removed; path={path}"

    def _is_referenced(self, host_id: str, path: str) -> bool:
        with self.database.session() as session:
            resources = session.scalars(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                )
            )
            for resource in resources:
                try:
                    disks = json.loads(resource.details_json).get("disks", [])
                except (AttributeError, json.JSONDecodeError):
                    continue
                if any(isinstance(disk, dict) and disk.get("source") == path for disk in disks):
                    return True
        return False

    def _media_item(self, item_id: str) -> MediaItem:
        with self.database.session() as session:
            item = session.get(MediaItem, item_id)
            if item is None or item.kind != MediaKind.ISO or item.status != MediaStatus.AVAILABLE:
                raise VmChangeConflict("platform ISO is unavailable")
            return item

    def _require_inactive(self, host_id: str, vm_uuid: str) -> None:
        if bool(self.discovery.read_one(host_id, vm_uuid).details.get("active")):
            raise VmChangeConflict("cached ISO changes require a shut-off VM")


def _payload(value: str) -> dict[str, object]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise VmChangeConflict("cached ISO change input is invalid") from exc
    if not isinstance(payload, dict):
        raise VmChangeConflict("cached ISO change input is invalid")
    return payload


def _offset(progress: ChangeProgress | None, amount: int) -> ChangeProgress | None:
    if progress is None:
        return None

    def shifted(sequence: int, message: str) -> None:
        progress(sequence + amount, message)

    return shifted
