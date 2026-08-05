"""Platform ISO cache fallback plans for hosts without QEMU HTTP support."""

import json
from dataclasses import asdict

from sqlalchemy import select

from nexora.config import Settings
from nexora.db import Database
from nexora.hosts.models import SudoMode
from nexora.media.iso_cache import MediaIsoCache, cache_path, cache_path_from_name
from nexora.media.models import MediaItem, MediaKind, MediaStatus
from nexora.remote.executor import RemoteExecutor
from nexora.remote.transfer import RemoteFileTransfer
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.cdrom_changes import VmCdromChangeService
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.cpu_changes import ChangeProgress, VmChangeConflict, VmChangePreview
from nexora.xml import CdromMediaChange, LibvirtXmlDocument, apply_cdrom_media


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
        current, original_xml, original_hash = self._current_persistent(vm_base)
        path = cache_path(item.sha256)
        change = CdromMediaChange(target, bus, expected_source, path)
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
        cache_path_from_name(expected_source)
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
        if plan.change_type == "cdrom_cache_mount":
            return self._execute_mount(plan_id, task_id, payload, expected_change_type, progress)
        result = super().execute(
            plan_id,
            task_id=task_id,
            expected_change_type=expected_change_type,
            progress=progress,
        )
        path = str(payload.get("expected_source", ""))
        self.discovery.run(plan.host_id)
        if self._cache_references(plan.host_id, path) == 0:
            try:
                self.cache.remove(plan.host_id, path, sudo=self._sudo(plan.host_id))
                return f"{result}; cache_removed=true"
            except RuntimeError:
                return f"{result}; cache_cleanup=manual"
        return f"{result}; cache_shared=true"

    def _execute_mount(
        self,
        plan_id: str,
        task_id: str,
        payload: dict[str, object],
        expected_change_type: str | None,
        progress: ChangeProgress | None,
    ) -> str:
        plan = self.plan_store.load(plan_id, VmChangePlanStatus.CONFIRMED)
        item = self._media_item(str(payload.get("media_item_id", "")))
        if item.sha256 != payload.get("media_sha256"):
            raise VmChangeConflict("platform ISO changed after preview")
        self.locks.acquire(plan.host_id, "media_cache", item.sha256, task_id)
        cached = None
        try:
            cached = self.cache.ensure(
                plan.host_id,
                item,
                task_id=task_id,
                sudo=self._sudo(plan.host_id),
                progress=progress,
            )
            result = super().execute(
                plan_id,
                task_id=task_id,
                expected_change_type=expected_change_type,
                progress=(
                    (lambda sequence, message: progress(sequence + 5, message))
                    if progress is not None
                    else None
                ),
            )
            return f"{result}; cache={cached.path}"
        except Exception:
            if cached is not None and cached.created:
                self.cache.remove(
                    plan.host_id,
                    cached.path,
                    sudo=self._sudo(plan.host_id),
                )
            raise
        finally:
            self.locks.release(plan.host_id, "media_cache", item.sha256, task_id)

    def _media_item(self, item_id: str) -> MediaItem:
        with self.database.session() as session:
            item = session.get(MediaItem, item_id)
            if item is None or item.kind != MediaKind.ISO or item.status != MediaStatus.AVAILABLE:
                raise VmChangeConflict("platform ISO is unavailable")
            return item

    def _require_inactive(self, host_id: str, vm_uuid: str) -> None:
        observation = self.discovery.read_one(host_id, vm_uuid)
        if bool(observation.details.get("active")):
            raise VmChangeConflict("cached ISO changes require a shut-off VM")

    def _sudo(self, host_id: str) -> bool:
        host = self._host(host_id)
        return host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS

    def _cache_references(self, host_id: str, path: str) -> int:
        with self.database.session() as session:
            domains = session.scalars(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.status != ResourceStatus.MISSING,
                )
            )
            return sum(
                1
                for domain in domains
                if any(
                    disk.get("source") == path
                    for disk in json.loads(domain.details_json).get("disks", [])
                )
            )


def _payload(value: str) -> dict[str, object]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise VmChangeConflict("cached ISO change input is invalid") from exc
    if not isinstance(payload, dict):
        raise VmChangeConflict("cached ISO change input is invalid")
    return payload
