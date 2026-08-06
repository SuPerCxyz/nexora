"""Preview, confirm, create a blank disk, and define a VM in one task."""

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
from nexora.remote.executor import CommandResult
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.storage.volume_contracts import StorageVolumeCreateInput
from nexora.storage.volume_remote import StorageVolumeRemoteCommands
from nexora.storage.volume_xml import build_volume_xml
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.blank_creation_authority import (
    VmBlankCreationAuthority,
    VmBlankCreationConflict,
)
from nexora.vms.blank_creation_contracts import VmBlankCreateInput
from nexora.vms.blank_creation_models import VmBlankCreationPlan
from nexora.vms.blank_creation_store import VmBlankCreationPlanStore
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.creation_remote import VmCreationRemote
from nexora.vms.creation_verify import created_vm_matches
from nexora.vms.creation_xml import build_import_domain_xml, creation_diff

PLAN_TTL = timedelta(minutes=10)
BlankCreationProgress = Callable[[int, str], None]


class VmBlankCreationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VmBlankCreationPreview:
    plan: VmBlankCreationPlan
    confirmation_token: str


class VmBlankCreationService:
    def __init__(
        self,
        database: Database,
        authority: VmBlankCreationAuthority,
        remote: VmCreationRemote,
        volume_commands: StorageVolumeRemoteCommands,
        locks: ResourceLockStore,
    ) -> None:
        self.database = database
        self.authority = authority
        self.remote = remote
        self.volume_commands = volume_commands
        self.locks = locks
        self.plans = VmBlankCreationPlanStore(database)

    def preview(self, create: VmBlankCreateInput) -> VmBlankCreationPreview:
        verified = self.authority.refresh_and_verify(create)
        volume_xml = build_volume_xml(_volume_input(create))
        self.volume_commands.validate_xml(create.host_id, volume_xml)
        proposed_xml = build_import_domain_xml(
            create,
            architecture=verified.architecture,
            disk_path=verified.disk_path,
            disk_format=verified.disk_format,
            iso_path=verified.iso_path,
            driver_iso_path=verified.driver_iso_path,
        )
        self.remote.validate_xml(create.host_id, proposed_xml)
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = VmBlankCreationPlan(
            id=str(uuid4()),
            host_id=create.host_id,
            vm_uuid=create.vm_uuid,
            vm_name=create.name,
            disk_name=create.disk_name,
            input_json=create.encode(),
            volume_xml=volume_xml,
            proposed_xml=proposed_xml,
            diff_text=creation_diff(proposed_xml),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=VmChangePlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return VmBlankCreationPreview(plan, token)

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
    ) -> VmBlankCreationPlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(VmBlankCreationPlan, plan_id)
            if plan is None or plan.status != VmChangePlanStatus.PREVIEW:
                raise VmBlankCreationError("blank-disk VM plan is unavailable")
            if plan.host_id != host_id or plan.vm_uuid != vm_uuid:
                raise VmBlankCreationConflict("blank-disk VM plan scope does not match")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = VmChangePlanStatus.EXPIRED
                raise VmBlankCreationError("blank-disk VM plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise VmBlankCreationError("blank-disk VM confirmation is invalid")
            plan.status = VmChangePlanStatus.CONFIRMED
            plan.confirmed_at = now
            return plan

    def execute(
        self,
        plan_id: str,
        *,
        task_id: str,
        progress: BlankCreationProgress | None = None,
    ) -> str:
        try:
            plan = self.plans.load_for_execution(plan_id)
        except ValueError as exc:
            raise VmBlankCreationError("blank-disk VM plan is not confirmed") from exc
        was_recovery = plan.status == VmChangePlanStatus.RUNNING
        create = VmBlankCreateInput.decode(plan.input_json)
        self._acquire_locks(create, task_id)
        try:
            self.plans.mark_running(plan.id)
            _notify(progress, 1, "Refresh authoritative pool and VM inventory")
            verified = self.authority.refresh_and_verify(create)
            existing_vm = self._existing_vm(create.host_id, create.vm_uuid)
            if existing_vm is not None:
                if not was_recovery or not self._matches(existing_vm, create):
                    raise VmBlankCreationConflict("VM name or UUID appeared after preview")
                self.plans.mark_succeeded(plan.id, existing_vm.id)
                return f"VM already matches blank-disk plan; vm={create.vm_uuid}"
            self._create_blank_disk(plan, create, task_id, progress)
            _notify(progress, 2, "Validate and define persistent VM without starting it")
            expected_xml = build_import_domain_xml(
                create,
                architecture=verified.architecture,
                disk_path=verified.disk_path,
                disk_format=verified.disk_format,
                iso_path=verified.iso_path,
                driver_iso_path=verified.driver_iso_path,
            )
            if expected_xml != plan.proposed_xml:
                raise VmBlankCreationConflict("blank-disk VM XML changed after preview")
            self.remote.validate_xml(create.host_id, expected_xml)
            self.remote.define(create.host_id, expected_xml)
            _notify(progress, 3, "Verify authoritative VM identity and blank disk")
            final = self._refresh_final(create)
            if not self._matches(final, create):
                raise VmBlankCreationError("blank-disk VM verification failed")
            self.plans.mark_succeeded(plan.id, final.id)
            return (
                f"VM created with blank disk; name={create.name}; "
                f"disk={create.disk_name}; vm={create.vm_uuid}; state=shutoff"
            )
        except Exception as exc:
            self.plans.mark_failed(plan.id, str(exc))
            raise
        finally:
            self._release_locks(create, task_id)

    def _create_blank_disk(
        self,
        plan: VmBlankCreationPlan,
        create: VmBlankCreateInput,
        task_id: str,
        progress: BlankCreationProgress | None,
    ) -> None:
        if plan.volume_xml != build_volume_xml(_volume_input(create)):
            raise VmBlankCreationConflict("blank disk XML changed after preview")
        result = self.volume_commands.virsh(
            create.host_id,
            ("vol-create", create.pool_uuid, "/dev/stdin"),
            stdin=plan.volume_xml,
        )
        _require_success(result)
        self.authority.storage.run(create.host_id)
        _notify(
            progress,
            2,
            "Created blank disk and refreshed authoritative storage inventory",
        )

    def _existing_vm(self, host_id: str, vm_uuid: str) -> ResourceIndex | None:
        with self.database.session() as session:
            return session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.native_id == vm_uuid,
                )
            )

    def _refresh_final(self, create: VmBlankCreateInput) -> ResourceIndex:
        self.authority.options.domains.run(create.host_id)
        final = self._existing_vm(create.host_id, create.vm_uuid)
        if final is None:
            raise VmBlankCreationError("created VM is absent from authoritative discovery")
        return final

    def _matches(self, resource: ResourceIndex, create: VmBlankCreateInput) -> bool:
        details: dict[str, object] = json.loads(resource.details_json)
        return (
            resource.display_name == create.name
            and resource.status == "managed"
            and created_vm_matches(
                details,
                create,
                disk_path=self._planned_volume_path(create),
                iso_path=self._iso_path(create),
            )
        )

    def _planned_volume_path(self, create: VmBlankCreateInput) -> str:
        return _volume_path(self.database, create.pool_uuid, create.disk_name)

    def _iso_path(self, create: VmBlankCreateInput) -> str:
        if create.iso_resource_id is None:
            return ""
        return _volume_path(self.database, create.pool_uuid, create.iso_name or "")

    def _acquire_locks(self, create: VmBlankCreateInput, task_id: str) -> None:
        acquired: list[tuple[str, str]] = []
        try:
            self.locks.acquire(
                create.host_id,
                ResourceType.STORAGE_POOL,
                create.pool_uuid,
                task_id,
            )
            acquired.append((ResourceType.STORAGE_POOL, create.pool_uuid))
            self.locks.acquire(
                create.host_id,
                ResourceType.VIRTUAL_MACHINE,
                create.vm_uuid,
                task_id,
            )
        except Exception:
            for resource_type, native_id in reversed(acquired):
                self.locks.release(create.host_id, resource_type, native_id, task_id)
            raise

    def _release_locks(self, create: VmBlankCreateInput, task_id: str) -> None:
        self.locks.release(
            create.host_id,
            ResourceType.VIRTUAL_MACHINE,
            create.vm_uuid,
            task_id,
        )
        self.locks.release(
            create.host_id,
            ResourceType.STORAGE_POOL,
            create.pool_uuid,
            task_id,
        )


def _volume_input(create: VmBlankCreateInput) -> StorageVolumeCreateInput:
    return StorageVolumeCreateInput(
        host_id=create.host_id,
        pool_resource_id=create.pool_resource_id,
        pool_uuid=create.pool_uuid,
        pool_generation=create.pool_generation,
        pool_hash=create.pool_hash,
        name=create.disk_name,
        volume_format=create.volume_format,
        capacity_bytes=create.capacity_bytes,
    )


def _volume_path(database: Database, pool_uuid: str, volume_name: str) -> str:
    if not volume_name:
        return ""
    from sqlalchemy import select

    with database.session() as session:
        pool = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                ResourceIndex.native_id == pool_uuid,
            )
        )
        if pool is None:
            return ""
        details: dict[str, object] = json.loads(pool.details_json)
        volume = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.resource_type == ResourceType.STORAGE_VOLUME,
                ResourceIndex.parent_native_id == pool_uuid,
                ResourceIndex.display_name == volume_name,
            )
        )
    path = details.get("target_path")
    if not isinstance(path, str):
        return ""
    if volume is not None:
        volume_details: dict[str, object] = json.loads(volume.details_json)
        value = volume_details.get("path")
        if isinstance(value, str):
            return value
    return f"{path.rstrip('/')}/{volume_name}"


def _notify(progress: BlankCreationProgress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)


def _require_success(result: CommandResult) -> None:
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    ):
        raise VmBlankCreationError("blank disk creation failed")
