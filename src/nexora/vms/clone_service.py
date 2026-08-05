"""Preview, confirm, execute, and verify shutdown full VM clones."""

import hmac
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select

from nexora.db import Database
from nexora.remote.commands import CommandSpec
from nexora.remote.relay import RelayResult, RemoteRelayTransfer
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.clone_authority import VmCloneAuthority, VmCloneConflict
from nexora.vms.clone_contracts import CloneFile, VmCloneManifest
from nexora.vms.clone_models import VmClonePlan
from nexora.vms.clone_remote import VmCloneRemote
from nexora.vms.clone_store import VmClonePlanStore
from nexora.vms.clone_xml import build_clone_xml, clone_xml_diff

CloneProgress = Callable[[int, float, str, str | None], None]
CancellationCheck = Callable[[], bool]
PLAN_TTL = timedelta(minutes=10)


class VmCloneError(RuntimeError):
    pass


@dataclass(frozen=True)
class VmClonePreview:
    plan: VmClonePlan
    manifest: VmCloneManifest
    confirmation_token: str


class VmCloneService:
    def __init__(
        self,
        database: Database,
        authority: VmCloneAuthority,
        remote: VmCloneRemote,
        relay: RemoteRelayTransfer,
        domains: DomainDiscoveryService,
        storage: StorageDiscoveryService,
        locks: ResourceLockStore,
    ) -> None:
        self.database = database
        self.authority = authority
        self.remote = remote
        self.relay = relay
        self.domains = domains
        self.storage = storage
        self.locks = locks
        self.plans = VmClonePlanStore(database)

    def preview(
        self,
        *,
        source_host_id: str,
        source_vm_uuid: str,
        source_resource_id: str,
        source_generation: int,
        source_hash: str,
        target_pool_id: str,
        target_name: str,
        preserve_identity: bool = False,
    ) -> VmClonePreview:
        plan_id = str(uuid4())
        manifest, source_xml = self.authority.build_manifest(
            source_host_id=source_host_id,
            source_vm_uuid=source_vm_uuid,
            source_resource_id=source_resource_id,
            source_generation=source_generation,
            source_hash=source_hash,
            target_pool_id=target_pool_id,
            target_name=target_name,
            plan_id=plan_id,
            preserve_identity=preserve_identity,
        )
        self._verify_target_identity(manifest)
        paths = {item.source_path: item.target_path for item in manifest.files}
        nvram = next((item.target_path for item in manifest.files if item.kind == "nvram"), None)
        target_xml = build_clone_xml(
            source_xml,
            name=manifest.target_name,
            vm_uuid=manifest.target_vm_uuid,
            disk_paths=paths,
            nvram_path=nvram,
            mac_addresses=manifest.mac_addresses,
        )
        self.remote.validate_xml(manifest.target_host_id, target_xml)
        for item in manifest.files:
            self.remote.target_available(
                manifest.target_host_id, item.target_path, item.partial_path
            )
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = VmClonePlan(
            id=plan_id,
            source_host_id=manifest.source_host_id,
            source_vm_uuid=manifest.source_vm_uuid,
            target_host_id=manifest.target_host_id,
            target_vm_uuid=manifest.target_vm_uuid,
            target_name=manifest.target_name,
            manifest_json=manifest.encode(),
            source_xml=source_xml,
            target_xml=target_xml,
            diff_text=clone_xml_diff(source_xml, target_xml),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=VmChangePlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return VmClonePreview(plan, manifest, token)

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        source_host_id: str,
        source_vm_uuid: str,
    ) -> VmClonePlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(VmClonePlan, plan_id)
            if plan is None or plan.status != VmChangePlanStatus.PREVIEW:
                raise VmCloneError("VM clone plan is unavailable")
            if plan.source_host_id != source_host_id or plan.source_vm_uuid != source_vm_uuid:
                raise VmCloneConflict("VM clone plan scope does not match")
            expires_at = plan.expires_at
            if (expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)) <= now:
                plan.status = VmChangePlanStatus.EXPIRED
                raise VmCloneError("VM clone plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise VmCloneError("VM clone confirmation is invalid")
            plan.status = VmChangePlanStatus.CONFIRMED
            plan.confirmed_at = now
            return plan

    def execute(
        self,
        plan_id: str,
        *,
        task_id: str,
        progress: CloneProgress | None = None,
        cancellation_requested: CancellationCheck | None = None,
    ) -> str:
        try:
            plan = self.plans.load_for_execution(plan_id)
        except ValueError as exc:
            raise VmCloneError("VM clone plan is not confirmed") from exc
        manifest = VmCloneManifest.decode(plan.manifest_json)
        was_recovery = plan.status == VmChangePlanStatus.RUNNING
        locks = self._acquire_locks(manifest, task_id)
        try:
            self.plans.mark_running(plan.id)
            _notify(progress, 1, 2, "Refresh source VM and target pool", None)
            self._verify_authority(
                manifest,
                plan.target_xml,
                allow_existing=was_recovery,
            )
            if was_recovery and self._existing_target(manifest) is not None:
                result = self._verify_result(manifest)
                self.plans.mark_succeeded(plan.id, result.id)
                return f"VM clone verified after recovery; target={manifest.target_vm_uuid}"
            self.remote.validate_xml(manifest.target_host_id, plan.target_xml)
            for offset, item in enumerate(manifest.files):
                self._copy_file(
                    manifest,
                    item,
                    offset,
                    task_id,
                    progress,
                    cancellation_requested,
                )
            _cancel(cancellation_requested)
            _notify(progress, len(manifest.files) + 2, 92, "Define cloned VM", None)
            self.remote.define(manifest.target_host_id, plan.target_xml)
            _notify(progress, len(manifest.files) + 3, 97, "Verify cloned VM", None)
            result = self._verify_result(manifest)
            self.plans.mark_succeeded(plan.id, result.id)
            return (
                f"VM cloned; source={manifest.source_vm_uuid}; "
                f"target={manifest.target_vm_uuid}; state=shutoff"
            )
        except Exception as exc:
            self.plans.mark_failed(plan.id, str(exc))
            raise
        finally:
            self._release_locks(locks, task_id)

    def _copy_file(
        self,
        manifest: VmCloneManifest,
        item: CloneFile,
        offset: int,
        task_id: str,
        progress: CloneProgress | None,
        cancellation_requested: CancellationCheck | None,
    ) -> None:
        info = self.remote.inspect_source(
            manifest.source_host_id,
            item.source_path,
            disk=item.kind == "disk",
        )
        if info.size_bytes != item.size_bytes:
            raise VmCloneConflict("clone source file size changed after preview")
        source_hash = self.remote.sha256(manifest.source_host_id, item.source_path)
        if self.remote.exists(manifest.target_host_id, item.target_path):
            target_info = self.remote.inspect_source(
                manifest.target_host_id,
                item.target_path,
                disk=item.kind == "disk",
            )
            target_hash = self.remote.sha256(manifest.target_host_id, item.target_path)
            if target_info.size_bytes == item.size_bytes and target_hash == source_hash:
                _notify(
                    progress,
                    offset + 2,
                    _file_progress(offset + 1, len(manifest.files)),
                    f"Verified previously published {item.kind}",
                    _checkpoint(item, source_hash, "published"),
                )
                return
            raise VmCloneConflict("clone target exists with different content")
        self.remote.cleanup_partial(manifest.target_host_id, item.partial_path)
        _cancel(cancellation_requested)
        self._transfer_and_publish(
            manifest,
            item,
            offset,
            source_hash,
            progress,
            cancellation_requested,
        )

    def _transfer_and_publish(
        self,
        manifest: VmCloneManifest,
        item: CloneFile,
        offset: int,
        source_hash: str,
        progress: CloneProgress | None,
        cancellation_requested: CancellationCheck | None,
    ) -> None:
        partial_owned = True
        try:
            result = self._relay_file(
                manifest,
                item,
                offset,
                source_hash,
                progress,
                cancellation_requested,
            )
            if (
                result.source_exit_code
                or result.target_exit_code
                or result.timed_out
                or result.cancelled
                or result.bytes_copied != item.size_bytes
            ):
                raise VmCloneError("clone file transfer failed or was interrupted")
            target_hash = self.remote.sha256(manifest.target_host_id, item.partial_path)
            if target_hash != source_hash:
                raise VmCloneError("clone file SHA-256 verification failed")
            self.remote.publish(manifest.target_host_id, item.partial_path, item.target_path)
            partial_owned = False
        finally:
            if partial_owned:
                self.remote.cleanup_partial(manifest.target_host_id, item.partial_path)
        _notify(
            progress,
            offset + 2,
            _file_progress(offset + 1, len(manifest.files)),
            f"Published cloned {item.kind}",
            _checkpoint(item, source_hash, "published"),
        )

    def _relay_file(
        self,
        manifest: VmCloneManifest,
        item: CloneFile,
        offset: int,
        source_hash: str,
        progress: CloneProgress | None,
        cancellation_requested: CancellationCheck | None,
    ) -> RelayResult:
        result = self.relay.copy(
            manifest.source_host_id,
            manifest.target_host_id,
            CommandSpec("dd", (f"if={item.source_path}", "bs=1048576", "status=none")),
            CommandSpec(
                "dd",
                (
                    f"of={item.partial_path}",
                    "bs=1048576",
                    "conv=fsync",
                    "status=none",
                ),
            ),
            source_sudo=self._sudo(manifest.source_host_id),
            target_sudo=self._sudo(manifest.target_host_id),
            timeout=86_400,
            operation_id=str(uuid4()),
            progress=lambda copied: _notify(
                progress,
                offset + 2,
                _copy_progress(offset, len(manifest.files), copied, item.size_bytes),
                f"Copied {copied} of {item.size_bytes} bytes",
                _checkpoint(item, source_hash, "copying", copied),
            ),
            cancellation_requested=cancellation_requested,
        )
        return result

    def _verify_authority(
        self,
        manifest: VmCloneManifest,
        target_xml: bytes,
        *,
        allow_existing: bool,
    ) -> None:
        self.domains.run(manifest.source_host_id)
        self.storage.run(manifest.target_host_id)
        with self.database.session() as session:
            source = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == manifest.source_host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.native_id == manifest.source_vm_uuid,
                )
            )
            pool = session.get(ResourceIndex, manifest.target_pool_id)
            if (
                source is None
                or source.observed_generation < manifest.source_generation
                or source.persistent_hash != manifest.source_hash
                or json.loads(source.details_json).get("active")
            ):
                raise VmCloneConflict("source VM changed after clone preview")
            if (
                pool is None
                or pool.host_id != manifest.target_host_id
                or pool.native_id != manifest.target_pool_uuid
                or pool.observed_generation < manifest.target_pool_generation
                or pool.persistent_hash != manifest.target_pool_hash
                or pool.status != ResourceStatus.MANAGED
            ):
                raise VmCloneConflict("target storage pool changed after clone preview")
        self._verify_target_identity(manifest, allow_existing=allow_existing)
        self.authority.verify_target_networks(manifest.target_host_id, target_xml)

    def _verify_target_identity(
        self,
        manifest: VmCloneManifest,
        *,
        allow_existing: bool = False,
    ) -> None:
        if self.remote.architecture(manifest.source_host_id) != self.remote.architecture(
            manifest.target_host_id
        ):
            raise VmCloneConflict("source and target host architectures differ")
        with self.database.session() as session:
            collision = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == manifest.target_host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.status != ResourceStatus.MISSING,
                    (
                        (ResourceIndex.native_id == manifest.target_vm_uuid)
                        | (ResourceIndex.display_name == manifest.target_name)
                    ),
                )
            )
        if collision is not None and not (
            allow_existing
            and collision.native_id == manifest.target_vm_uuid
            and collision.display_name == manifest.target_name
        ):
            raise VmCloneConflict("clone target VM name or UUID already exists")

    def _existing_target(self, manifest: VmCloneManifest) -> ResourceIndex | None:
        with self.database.session() as session:
            resource = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == manifest.target_host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.native_id == manifest.target_vm_uuid,
                    ResourceIndex.status != ResourceStatus.MISSING,
                )
            )
            if resource is not None:
                session.expunge(resource)
            return resource

    def _verify_result(self, manifest: VmCloneManifest) -> ResourceIndex:
        self.storage.run(manifest.target_host_id)
        self.domains.run(manifest.target_host_id)
        with self.database.session() as session:
            resource = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == manifest.target_host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.native_id == manifest.target_vm_uuid,
                )
            )
            if resource is None:
                raise VmCloneError("cloned VM is absent from authoritative discovery")
            details = json.loads(resource.details_json)
            actual_paths = {
                str(item.get("source"))
                for item in details.get("disks", [])
                if isinstance(item, dict) and item.get("device") == "disk"
            }
            expected_paths = {item.target_path for item in manifest.files if item.kind == "disk"}
            if (
                resource.display_name != manifest.target_name
                or details.get("active")
                or not details.get("persistent")
                or not expected_paths <= actual_paths
            ):
                raise VmCloneError("cloned VM authoritative verification failed")
            session.expunge(resource)
            return resource

    def _acquire_locks(
        self,
        manifest: VmCloneManifest,
        task_id: str,
    ) -> list[tuple[str, ResourceType, str]]:
        identities = {
            (
                manifest.source_host_id,
                ResourceType.VIRTUAL_MACHINE,
                manifest.source_vm_uuid,
            ),
            (
                manifest.target_host_id,
                ResourceType.VIRTUAL_MACHINE,
                manifest.target_vm_uuid,
            ),
            (
                manifest.target_host_id,
                ResourceType.STORAGE_POOL,
                manifest.target_pool_uuid,
            ),
            *{
                (manifest.target_host_id, ResourceType.STORAGE_VOLUME, item.target_path)
                for item in manifest.files
            },
            *{
                (manifest.source_host_id, ResourceType.STORAGE_VOLUME, item.source_path)
                for item in manifest.files
            },
        }
        ordered = sorted(identities, key=lambda item: (item[0], item[1].value, item[2]))
        acquired: list[tuple[str, ResourceType, str]] = []
        try:
            for host_id, resource_type, native_id in ordered:
                self.locks.acquire(host_id, resource_type, native_id, task_id)
                acquired.append((host_id, resource_type, native_id))
            return acquired
        except Exception:
            self._release_locks(acquired, task_id)
            raise

    def _release_locks(
        self,
        acquired: list[tuple[str, ResourceType, str]],
        task_id: str,
    ) -> None:
        for host_id, resource_type, native_id in reversed(acquired):
            self.locks.release(host_id, resource_type, native_id, task_id)

    def _sudo(self, host_id: str) -> bool:
        from nexora.hosts.models import Host, SudoMode

        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise VmCloneError("clone host disappeared")
            return host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS


def _notify(
    callback: CloneProgress | None,
    sequence: int,
    percentage: float,
    message: str,
    checkpoint: str | None,
) -> None:
    if callback is not None:
        callback(sequence, min(99, percentage), message, checkpoint)


def _cancel(check: CancellationCheck | None) -> None:
    if check is not None and check():
        raise VmCloneError("VM clone was cancelled")


def _copy_progress(offset: int, total: int, copied: int, size: int) -> float:
    file_fraction = copied / max(1, size)
    return 5 + ((offset + file_fraction) / max(1, total)) * 82


def _file_progress(completed: int, total: int) -> float:
    return 5 + completed / max(1, total) * 82


def _checkpoint(
    item: CloneFile,
    digest: str,
    status: str,
    copied: int | None = None,
) -> str:
    return json.dumps(
        {
            "source": item.source_path,
            "partial": item.partial_path,
            "final": item.target_path,
            "size": item.size_bytes,
            "sha256": digest,
            "status": status,
            "copied": copied,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
