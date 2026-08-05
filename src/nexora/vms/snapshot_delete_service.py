"""Preview, confirm, execute, and verify internal leaf Snapshot deletion."""

import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.conflicts import ResourceWriteGuard
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.snapshot_discovery import SnapshotDiscoveryService
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.snapshot_contracts import SnapshotDeleteInput, SnapshotRevertInput
from nexora.vms.snapshot_errors import SnapshotChangeConflict, SnapshotChangeError
from nexora.vms.snapshot_models import SnapshotChangePlan
from nexora.vms.snapshot_plan_store import SnapshotPlanStore
from nexora.vms.snapshot_service import PLAN_TTL, SnapshotPreview, _require_success
from nexora.vms.snapshot_validation import deletion_diff, supported_disks, validate_deletable

ChangeProgress = Callable[[int, str], None]
SnapshotTargetInput = SnapshotDeleteInput | SnapshotRevertInput


@dataclass
class SnapshotDeleteService:
    database: Database
    executor: RemoteExecutor
    domains: DomainDiscoveryService
    snapshots: SnapshotDiscoveryService
    store: ResourceIndexStore
    guard: ResourceWriteGuard
    locks: ResourceLockStore

    def __post_init__(self) -> None:
        self.plans = SnapshotPlanStore(self.database)

    def preview(self, delete: SnapshotDeleteInput) -> SnapshotPreview:
        delete.validate()
        self._refresh_vm(delete)
        self.snapshots.run(delete.vm_base.host_id)
        target, inventory = self._target_and_inventory(delete)
        validate_deletable(delete, target, inventory)
        assert target is not None
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = SnapshotChangePlan(
            id=str(uuid4()),
            host_id=delete.vm_base.host_id,
            operation="delete",
            vm_resource_id=delete.vm_base.resource_id,
            vm_uuid=delete.vm_base.native_id,
            snapshot_name=delete.name,
            vm_generation=delete.vm_base.generation,
            vm_hash=delete.vm_base.persistent_hash,
            snapshot_resource_id=delete.snapshot_base.resource_id,
            snapshot_generation=delete.snapshot_base.generation,
            snapshot_hash=delete.snapshot_base.persistent_hash,
            input_json=delete.encode(),
            diff_text=deletion_diff(delete, target),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=VmChangePlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return SnapshotPreview(plan, token)

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
        snapshot_name: str,
    ) -> SnapshotChangePlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(SnapshotChangePlan, plan_id)
            if plan is None or plan.status != VmChangePlanStatus.PREVIEW:
                raise SnapshotChangeError("Snapshot delete plan is unavailable")
            if (
                plan.host_id != host_id
                or plan.vm_uuid != vm_uuid
                or plan.snapshot_name != snapshot_name
                or plan.operation != "delete"
            ):
                raise SnapshotChangeConflict("Snapshot delete plan scope does not match")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = VmChangePlanStatus.EXPIRED
                raise SnapshotChangeError("Snapshot delete plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise SnapshotChangeError("Snapshot delete confirmation is invalid")
            plan.status = VmChangePlanStatus.CONFIRMED
            plan.confirmed_at = now
            return plan

    def execute(
        self,
        plan_id: str,
        *,
        task_id: str,
        progress: ChangeProgress | None = None,
    ) -> str:
        try:
            plan = self.plans.load_confirmed(plan_id)
        except ValueError as exc:
            raise SnapshotChangeError("Snapshot delete plan is not confirmed") from exc
        delete = SnapshotDeleteInput.decode(plan.input_json)
        self.locks.acquire(
            plan.host_id,
            ResourceType.VIRTUAL_MACHINE,
            plan.vm_uuid,
            task_id,
        )
        try:
            self.locks.acquire(
                plan.host_id,
                ResourceType.SNAPSHOT,
                delete.snapshot_base.native_id,
                task_id,
            )
            return self._execute_locked(plan, delete, progress)
        finally:
            self.locks.release(
                plan.host_id,
                ResourceType.SNAPSHOT,
                delete.snapshot_base.native_id,
                task_id,
            )
            self.locks.release(
                plan.host_id,
                ResourceType.VIRTUAL_MACHINE,
                plan.vm_uuid,
                task_id,
            )

    def _execute_locked(
        self,
        plan: SnapshotChangePlan,
        delete: SnapshotDeleteInput,
        progress: ChangeProgress | None,
    ) -> str:
        try:
            self.plans.mark_running(plan.id)
            _notify(progress, 1, "Refresh authoritative VM and Snapshot topology")
            self._refresh_vm(delete)
            self.snapshots.run(plan.host_id)
            target, inventory = self._target_and_inventory(delete)
            validate_deletable(delete, target, inventory)
            other_hashes = {
                item.id: item.persistent_hash
                for item in inventory
                if item.id != delete.snapshot_base.resource_id
            }
            _notify(progress, 2, "Delete internal leaf Snapshot")
            _require_success(self._delete_command(delete))
            _notify(progress, 3, "Verify Snapshot removal and preserved VM XML")
            self.snapshots.run(plan.host_id)
            self._verify_deleted(delete, other_hashes)
            self._refresh_vm(delete)
            self.plans.mark_succeeded(plan.id)
            return f"Snapshot deleted; vm={plan.vm_uuid}; name={plan.snapshot_name}"
        except Exception as exc:
            self.plans.mark_failed(plan.id, str(exc))
            raise

    def _refresh_vm(self, delete: SnapshotTargetInput) -> None:
        observation = self.domains.read_one(
            delete.vm_base.host_id,
            delete.vm_base.native_id,
        )
        self.store.refresh_one(
            delete.vm_base.host_id,
            ResourceType.VIRTUAL_MACHINE,
            observation,
        )
        self.guard.verify(delete.vm_base)
        if observation.persistent_hash is None:
            raise SnapshotChangeConflict("Snapshot deletion requires a persistent VM")
        if bool(observation.details.get("active")):
            raise SnapshotChangeConflict("Snapshot deletion requires a shut-off VM")
        supported_disks(observation)

    def _target_and_inventory(
        self,
        delete: SnapshotTargetInput,
    ) -> tuple[ResourceIndex | None, list[ResourceIndex]]:
        inventory = self._inventory(delete.vm_base.host_id)
        active = [
            item
            for item in inventory
            if item.parent_native_id == delete.vm_base.native_id
            and item.status != ResourceStatus.MISSING
        ]
        target = next(
            (item for item in active if item.native_id == delete.snapshot_base.native_id),
            None,
        )
        return target, active

    def _verify_deleted(
        self,
        delete: SnapshotDeleteInput,
        other_hashes: dict[str, str | None],
    ) -> None:
        inventory = self._inventory(delete.vm_base.host_id)
        target = next(
            (item for item in inventory if item.id == delete.snapshot_base.resource_id),
            None,
        )
        if target is None or target.status != ResourceStatus.MISSING:
            raise SnapshotChangeError("deleted Snapshot is still present")
        current_hashes = {
            item.id: item.persistent_hash
            for item in inventory
            if item.id in other_hashes and item.status != ResourceStatus.MISSING
        }
        if current_hashes != other_hashes:
            raise SnapshotChangeConflict("another Snapshot changed during deletion")

    def _inventory(self, host_id: str) -> list[ResourceIndex]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(ResourceIndex).where(
                        ResourceIndex.host_id == host_id,
                        ResourceIndex.resource_type == ResourceType.SNAPSHOT,
                    )
                )
            )

    def _delete_command(self, delete: SnapshotDeleteInput) -> CommandResult:
        host = self._host(delete.vm_base.host_id)
        return self.executor.run(
            delete.vm_base.host_id,
            CommandSpec(
                "virsh",
                (
                    "-c",
                    host.libvirt_uri,
                    "snapshot-delete",
                    delete.vm_base.native_id,
                    delete.name,
                ),
            ),
            sudo=host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS,
            timeout=3_600,
            env={"LC_ALL": "C"},
        )

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise SnapshotChangeError("host not found")
            return host


def _notify(progress: ChangeProgress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)
