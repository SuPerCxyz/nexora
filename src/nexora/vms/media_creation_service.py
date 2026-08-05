"""Preview and execute platform-image VM creation."""

import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select

from nexora.db import Database
from nexora.media.copy import MediaImageCopyService
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.cloud_init import build_cloud_init_documents, cloud_init_seed_name
from nexora.vms.cloud_init_remote import CloudInitRemote
from nexora.vms.creation_remote import VmCreationRemote
from nexora.vms.creation_xml import build_import_domain_xml, creation_diff
from nexora.vms.image_resize import ImageResizeRemote
from nexora.vms.media_creation_authority import (
    VmMediaCreationAuthority,
    VmMediaCreationConflict,
    media_copy_input,
)
from nexora.vms.media_creation_contracts import VmMediaCreateInput
from nexora.vms.media_creation_models import VmMediaCreationPlan
from nexora.vms.media_creation_store import VmMediaCreationPlanStore
from nexora.vms.media_creation_verify import MediaCreationVerifier

PLAN_TTL = timedelta(minutes=10)
MediaCreationProgress = Callable[[int, float, str], None]
CancellationCheck = Callable[[], bool]


class VmMediaCreationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VmMediaCreationPreview:
    plan: VmMediaCreationPlan
    confirmation_token: str
    target_path: str


class VmMediaCreationService:
    def __init__(
        self,
        database: Database,
        authority: VmMediaCreationAuthority,
        copier: MediaImageCopyService,
        remote: VmCreationRemote,
        storage: StorageDiscoveryService,
        domains: DomainDiscoveryService,
        locks: ResourceLockStore,
        cloud_init: CloudInitRemote | None = None,
        image_resize: ImageResizeRemote | None = None,
    ) -> None:
        self.database = database
        self.authority = authority
        self.copier = copier
        self.remote = remote
        self.storage = storage
        self.domains = domains
        self.locks = locks
        self.cloud_init = cloud_init
        self.image_resize = image_resize
        self.verifier = MediaCreationVerifier(database)
        self.plans = VmMediaCreationPlanStore(database)

    def preview(self, create: VmMediaCreateInput) -> VmMediaCreationPreview:
        plan_id = str(uuid4())
        verified = self.authority.verify(create, task_id=plan_id)
        documents = build_cloud_init_documents(create)
        if documents is not None:
            self._cloud_remote().probe(create.host_id)
        proposed_xml = build_import_domain_xml(
            create,
            architecture=verified.architecture,
            disk_path=verified.disk_path,
            disk_format=create.media_format,
            iso_path=verified.iso_path,
            driver_iso_path=verified.driver_iso_path,
            cloud_init_path=verified.cloud_init_path,
        )
        self.remote.validate_xml(create.host_id, proposed_xml)
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = VmMediaCreationPlan(
            id=plan_id,
            host_id=create.host_id,
            media_item_id=create.media_item_id,
            vm_uuid=create.vm_uuid,
            vm_name=create.name,
            input_json=create.encode(),
            proposed_xml=proposed_xml,
            diff_text=creation_diff(proposed_xml),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=VmChangePlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return VmMediaCreationPreview(plan, token, verified.disk_path)

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
    ) -> VmMediaCreationPlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(VmMediaCreationPlan, plan_id)
            if plan is None or plan.status != VmChangePlanStatus.PREVIEW:
                raise VmMediaCreationError("platform-image VM plan is unavailable")
            if plan.host_id != host_id or plan.vm_uuid != vm_uuid:
                raise VmMediaCreationConflict("platform-image VM plan scope changed")
            expires = plan.expires_at
            if (expires.replace(tzinfo=UTC) if expires.tzinfo is None else expires) <= now:
                plan.status = VmChangePlanStatus.EXPIRED
                raise VmMediaCreationError("platform-image VM plan expired")
            digest = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(digest, plan.confirmation_digest):
                raise VmMediaCreationError("platform-image VM confirmation is invalid")
            plan.status = VmChangePlanStatus.CONFIRMED
            plan.confirmed_at = now
            return plan

    def execute(
        self,
        plan_id: str,
        *,
        task_id: str,
        progress: MediaCreationProgress | None = None,
        cancellation_requested: CancellationCheck | None = None,
    ) -> str:
        try:
            plan = self.plans.load_for_execution(plan_id)
        except ValueError as exc:
            raise VmMediaCreationError("platform-image VM plan is not confirmed") from exc
        create = VmMediaCreateInput.decode(plan.input_json)
        self._acquire_locks(create, task_id)
        try:
            self.plans.mark_running(plan.id)
            existing = self._existing(create.host_id, create.vm_uuid)
            if existing is not None:
                return self._finish_existing(plan, create, existing)
            _notify(progress, 1, 1, "Refresh authoritative source, target, and VM identity")
            verified = self.authority.verify(create, task_id=task_id)
            expected_xml = build_import_domain_xml(
                create,
                architecture=verified.architecture,
                disk_path=verified.disk_path,
                disk_format=create.media_format,
                iso_path=verified.iso_path,
                driver_iso_path=verified.driver_iso_path,
                cloud_init_path=verified.cloud_init_path,
            )
            if expected_xml != plan.proposed_xml:
                raise VmMediaCreationConflict("platform-image VM XML changed after preview")
            self._copy_and_resize(
                plan,
                create,
                verified.disk_path,
                task_id,
                progress,
                cancellation_requested,
            )
            documents = build_cloud_init_documents(create)
            if documents is not None:
                if verified.cloud_init_path is None:
                    raise VmMediaCreationError("cloud-init seed path is unavailable")
                _notify(progress, 2, 77, "Generate and verify NoCloud seed ISO")
                self._cloud_remote().publish(
                    create.host_id,
                    verified.cloud_init_path,
                    documents,
                    task_id=task_id,
                )
            _notify(progress, 3, 80, "Refresh target Pool and discover copied Volume")
            self.remote.refresh_pool(create.host_id, create.pool_uuid)
            self.storage.run(create.host_id)
            self.verifier.copied_volume(create, verified.disk_path)
            self.verifier.seed_volume(create, verified.cloud_init_path)
            _notify(progress, 4, 90, "Validate and define persistent VM")
            self.remote.validate_xml(create.host_id, expected_xml)
            self.remote.define(create.host_id, expected_xml)
            _notify(progress, 5, 97, "Verify authoritative VM and copied system disk")
            self.domains.run(create.host_id)
            final = self._existing(create.host_id, create.vm_uuid)
            if final is None or not self.verifier.vm_matches(final, create, expected_xml):
                raise VmMediaCreationError("platform-image VM verification failed")
            self.plans.mark_succeeded(plan.id, final.id)
            return f"VM created from platform image; name={create.name}; vm={create.vm_uuid}"
        except Exception as exc:
            self.plans.mark_failed(plan.id, str(exc))
            raise
        finally:
            self._release_locks(create, task_id)

    def _copy_and_resize(
        self,
        plan: VmMediaCreationPlan,
        create: VmMediaCreateInput,
        disk_path: str,
        task_id: str,
        progress: MediaCreationProgress | None,
        cancellation_requested: CancellationCheck | None,
    ) -> None:
        target = create.target_capacity_bytes
        source = create.source_virtual_size_bytes
        if target is None:
            self._copy(create, task_id, progress, cancellation_requested)
            return
        if source is None or self.image_resize is None:
            raise VmMediaCreationError("image resize metadata or service is unavailable")
        if target == source:
            self._copy(create, task_id, progress, cancellation_requested)
            return
        current = self.image_resize.virtual_size(create.host_id, disk_path)
        if current == target:
            digest = self.image_resize.sha256(create.host_id, disk_path)
            if plan.resized_image_sha256 is None or digest != plan.resized_image_sha256:
                raise VmMediaCreationConflict(
                    "resized target exists without the planned verification hash"
                )
            _notify(progress, 2, 76, "Verified previously resized system disk")
            return
        if current not in {None, source}:
            raise VmMediaCreationConflict("target image has an unexpected virtual size")
        self._copy(create, task_id, progress, cancellation_requested)
        _notify(progress, 2, 73, "Grow copied system disk")
        self.image_resize.grow(create.host_id, disk_path, source, target)
        digest = self.image_resize.sha256(create.host_id, disk_path)
        self.plans.record_resized_hash(plan.id, digest)
        plan.resized_image_sha256 = digest

    def _copy(
        self,
        create: VmMediaCreateInput,
        task_id: str,
        progress: MediaCreationProgress | None,
        cancellation_requested: CancellationCheck | None,
    ) -> None:
        self.copier.execute(
            media_copy_input(create),
            task_id=task_id,
            progress=lambda _step, percent, message: _notify(
                progress, 2, 5 + percent * 0.65, message
            ),
            cancellation_requested=cancellation_requested,
        )

    def _finish_existing(
        self,
        plan: VmMediaCreationPlan,
        create: VmMediaCreateInput,
        existing: ResourceIndex,
    ) -> str:
        if plan.status != VmChangePlanStatus.RUNNING or not self.verifier.vm_matches(
            existing, create, plan.proposed_xml
        ):
            raise VmMediaCreationConflict("VM name or UUID already exists")
        self._verify_recovered_resize(plan, create)
        self.plans.mark_succeeded(plan.id, existing.id)
        return f"VM already matches recovered platform-image plan; vm={create.vm_uuid}"

    def _verify_recovered_resize(
        self,
        plan: VmMediaCreationPlan,
        create: VmMediaCreateInput,
    ) -> None:
        target = create.target_capacity_bytes
        source = create.source_virtual_size_bytes
        if target is None or target == source:
            return
        if self.image_resize is None or plan.resized_image_sha256 is None:
            raise VmMediaCreationConflict("recovered resized image lacks verification metadata")
        disk_path = self.verifier.disk_path(plan.proposed_xml)
        if self.image_resize.virtual_size(create.host_id, disk_path) != target:
            raise VmMediaCreationConflict("recovered image capacity changed")
        digest = self.image_resize.sha256(create.host_id, disk_path)
        if digest != plan.resized_image_sha256:
            raise VmMediaCreationConflict("recovered resized image hash changed")

    def _existing(self, host_id: str, vm_uuid: str) -> ResourceIndex | None:
        self.domains.run(host_id)
        with self.database.session() as session:
            return session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.native_id == vm_uuid,
                )
            )

    def _acquire_locks(self, create: VmMediaCreateInput, task_id: str) -> None:
        identities = [
            ("storage_file", f"{create.pool_uuid}/{create.target_file_name}"),
            (ResourceType.VIRTUAL_MACHINE, create.vm_uuid),
        ]
        if create.iso_native_id is not None:
            identities.insert(1, (ResourceType.STORAGE_VOLUME, create.iso_native_id))
        seed_name = cloud_init_seed_name(create)
        if seed_name is not None:
            identities.insert(1, ("storage_file", f"{create.pool_uuid}/{seed_name}"))
        acquired: list[tuple[str, str]] = []
        try:
            for resource_type, resource_id in identities:
                self.locks.acquire(create.host_id, resource_type, resource_id, task_id)
                acquired.append((resource_type, resource_id))
        except Exception:
            for resource_type, resource_id in reversed(acquired):
                self.locks.release(create.host_id, resource_type, resource_id, task_id)
            raise

    def _release_locks(self, create: VmMediaCreateInput, task_id: str) -> None:
        identities = [
            (ResourceType.VIRTUAL_MACHINE, create.vm_uuid),
            *(
                [(ResourceType.STORAGE_VOLUME, create.iso_native_id)]
                if create.iso_native_id
                else []
            ),
            ("storage_file", f"{create.pool_uuid}/{create.target_file_name}"),
        ]
        seed_name = cloud_init_seed_name(create)
        if seed_name is not None:
            identities.insert(-1, ("storage_file", f"{create.pool_uuid}/{seed_name}"))
        for resource_type, resource_id in identities:
            self.locks.release(create.host_id, resource_type, resource_id, task_id)

    def _cloud_remote(self) -> CloudInitRemote:
        if self.cloud_init is None:
            raise VmMediaCreationError("cloud-init remote service is unavailable")
        return self.cloud_init


def _notify(
    progress: MediaCreationProgress | None,
    sequence: int,
    percentage: float,
    message: str,
) -> None:
    if progress is not None:
        progress(sequence, min(99, percentage), message)
