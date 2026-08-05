"""Preview, confirm, define, and verify managed-volume VM imports."""

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
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.creation_authority import VmCreationAuthority, VmCreationConflict
from nexora.vms.creation_contracts import VmImportCreateInput
from nexora.vms.creation_models import VmCreationPlan
from nexora.vms.creation_remote import VmCreationRemote
from nexora.vms.creation_store import VmCreationPlanStore
from nexora.vms.creation_verify import created_vm_matches
from nexora.vms.creation_xml import build_import_domain_xml, creation_diff

PLAN_TTL = timedelta(minutes=10)
CreationProgress = Callable[[int, str], None]


class VmCreationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VmCreationPreview:
    plan: VmCreationPlan
    confirmation_token: str


class VmCreationService:
    def __init__(
        self,
        database: Database,
        authority: VmCreationAuthority,
        remote: VmCreationRemote,
        domains: DomainDiscoveryService,
        resources: ResourceIndexStore,
        locks: ResourceLockStore,
    ) -> None:
        self.database = database
        self.authority = authority
        self.remote = remote
        self.domains = domains
        self.resources = resources
        self.locks = locks
        self.plans = VmCreationPlanStore(database)

    def preview(self, create: VmImportCreateInput) -> VmCreationPreview:
        verified = self.authority.refresh_and_verify(create)
        proposed_xml = build_import_domain_xml(
            create,
            architecture=verified.architecture,
            disk_path=verified.path,
            disk_format=verified.disk_format,
            iso_path=verified.iso_path,
            driver_iso_path=verified.driver_iso_path,
        )
        self.remote.validate_xml(create.host_id, proposed_xml)
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = VmCreationPlan(
            id=str(uuid4()),
            host_id=create.host_id,
            volume_resource_id=create.volume_resource_id,
            volume_native_id=create.volume_native_id,
            volume_generation=create.volume_generation,
            volume_hash=create.volume_hash,
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
        return VmCreationPreview(plan, token)

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
    ) -> VmCreationPlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(VmCreationPlan, plan_id)
            if plan is None or plan.status != VmChangePlanStatus.PREVIEW:
                raise VmCreationError("VM creation plan is unavailable")
            if plan.host_id != host_id or plan.vm_uuid != vm_uuid:
                raise VmCreationConflict("VM creation plan scope does not match")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = VmChangePlanStatus.EXPIRED
                raise VmCreationError("VM creation plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise VmCreationError("VM creation confirmation is invalid")
            plan.status = VmChangePlanStatus.CONFIRMED
            plan.confirmed_at = now
            return plan

    def execute(
        self,
        plan_id: str,
        *,
        task_id: str,
        progress: CreationProgress | None = None,
    ) -> str:
        try:
            plan = self.plans.load_for_execution(plan_id)
        except ValueError as exc:
            raise VmCreationError("VM creation plan is not confirmed") from exc
        was_recovery = plan.status == VmChangePlanStatus.RUNNING
        create = VmImportCreateInput.decode(plan.input_json)
        self._acquire_locks(create, task_id)
        try:
            self.plans.mark_running(plan.id)
            _notify(progress, 1, "Refresh authoritative VM and storage inventory")
            self.domains.run(create.host_id)
            existing = self._existing(create.host_id, create.vm_uuid)
            if existing is not None:
                if not was_recovery or not self._matches(existing, create):
                    raise VmCreationConflict("VM name or UUID appeared after preview")
                self.plans.mark_succeeded(plan.id, existing.id)
                return f"VM already matches plan; vm={create.vm_uuid}"
            verified = self.authority.refresh_and_verify(create)
            expected_xml = build_import_domain_xml(
                create,
                architecture=verified.architecture,
                disk_path=verified.path,
                disk_format=verified.disk_format,
                iso_path=verified.iso_path,
                driver_iso_path=verified.driver_iso_path,
            )
            if expected_xml != plan.proposed_xml:
                raise VmCreationConflict("VM creation XML changed after preview")
            self.remote.validate_xml(create.host_id, expected_xml)
            _notify(progress, 2, "Define persistent VM without starting it")
            self.remote.define(create.host_id, expected_xml)
            _notify(progress, 3, "Verify authoritative VM identity and disk")
            final = self._refresh_final(create)
            if not self._matches(final, create):
                raise VmCreationError("created VM verification failed")
            self.plans.mark_succeeded(plan.id, final.id)
            return f"VM created; name={create.name}; vm={create.vm_uuid}; state=shutoff"
        except Exception as exc:
            self.plans.mark_failed(plan.id, str(exc))
            raise
        finally:
            self._release_locks(create, task_id)

    def _acquire_locks(self, create: VmImportCreateInput, task_id: str) -> None:
        acquired: list[str] = []
        try:
            for native_id in _volume_lock_ids(create):
                self.locks.acquire(
                    create.host_id,
                    ResourceType.STORAGE_VOLUME,
                    native_id,
                    task_id,
                )
                acquired.append(native_id)
            self.locks.acquire(
                create.host_id,
                ResourceType.VIRTUAL_MACHINE,
                create.vm_uuid,
                task_id,
            )
        except Exception:
            for native_id in reversed(acquired):
                self.locks.release(
                    create.host_id,
                    ResourceType.STORAGE_VOLUME,
                    native_id,
                    task_id,
                )
            raise

    def _release_locks(self, create: VmImportCreateInput, task_id: str) -> None:
        self.locks.release(
            create.host_id,
            ResourceType.VIRTUAL_MACHINE,
            create.vm_uuid,
            task_id,
        )
        for native_id in reversed(_volume_lock_ids(create)):
            self.locks.release(
                create.host_id,
                ResourceType.STORAGE_VOLUME,
                native_id,
                task_id,
            )

    def _existing(self, host_id: str, vm_uuid: str) -> ResourceIndex | None:
        with self.database.session() as session:
            return session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.native_id == vm_uuid,
                )
            )

    def _refresh_final(self, create: VmImportCreateInput) -> ResourceIndex:
        self.domains.run(create.host_id)
        final = self._existing(create.host_id, create.vm_uuid)
        if final is None:
            raise VmCreationError("created VM is absent from authoritative discovery")
        return final

    def _matches(self, resource: ResourceIndex, create: VmImportCreateInput) -> bool:
        details: dict[str, object] = json.loads(resource.details_json)
        return (
            resource.display_name == create.name
            and resource.status == "managed"
            and created_vm_matches(
                details,
                create,
                disk_path=self._planned_volume_path(create.volume_resource_id),
                iso_path=self._planned_volume_path(create.iso_resource_id),
            )
        )

    def _planned_volume_path(self, resource_id: str | None) -> str:
        if resource_id is None:
            return ""
        with self.database.session() as session:
            volume = session.get(ResourceIndex, resource_id)
            if volume is None:
                return ""
            details: dict[str, object] = json.loads(volume.details_json)
        path = details.get("path")
        return path if isinstance(path, str) else ""


def _notify(progress: CreationProgress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)


def _volume_lock_ids(create: VmImportCreateInput) -> list[str]:
    return sorted(
        {create.volume_native_id, *([create.iso_native_id] if create.iso_native_id else [])}
    )
