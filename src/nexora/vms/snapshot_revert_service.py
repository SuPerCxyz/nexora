"""Strict disk-only revert for a configuration-equivalent current Snapshot."""

import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from nexora.db import Database
from nexora.hosts.models import SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.conflicts import ResourceWriteGuard
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.resources.snapshot_discovery import SnapshotDiscoveryService
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.snapshot_contracts import SnapshotRevertInput
from nexora.vms.snapshot_delete_service import SnapshotDeleteService
from nexora.vms.snapshot_errors import SnapshotChangeConflict, SnapshotChangeError
from nexora.vms.snapshot_models import SnapshotChangePlan
from nexora.vms.snapshot_service import PLAN_TTL, SnapshotPreview, _require_success
from nexora.vms.snapshot_validation import revert_diff, validate_revertable

ChangeProgress = Callable[[int, str], None]


@dataclass
class SnapshotRevertService:
    database: Database
    executor: RemoteExecutor
    domains: DomainDiscoveryService
    snapshots: SnapshotDiscoveryService
    store: ResourceIndexStore
    guard: ResourceWriteGuard
    locks: ResourceLockStore

    def __post_init__(self) -> None:
        self.shared = SnapshotDeleteService(
            self.database,
            self.executor,
            self.domains,
            self.snapshots,
            self.store,
            self.guard,
            self.locks,
        )
        self.plans = self.shared.plans

    def preview(self, revert: SnapshotRevertInput) -> SnapshotPreview:
        revert.validate()
        self.shared._refresh_vm(revert)
        self.snapshots.run(revert.vm_base.host_id)
        target, inventory = self.shared._target_and_inventory(revert)
        validate_revertable(revert, target, inventory)
        assert target is not None
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = SnapshotChangePlan(
            id=str(uuid4()),
            host_id=revert.vm_base.host_id,
            operation="revert",
            vm_resource_id=revert.vm_base.resource_id,
            vm_uuid=revert.vm_base.native_id,
            snapshot_name=revert.name,
            vm_generation=revert.vm_base.generation,
            vm_hash=revert.vm_base.persistent_hash,
            snapshot_resource_id=revert.snapshot_base.resource_id,
            snapshot_generation=revert.snapshot_base.generation,
            snapshot_hash=revert.snapshot_base.persistent_hash,
            input_json=revert.encode(),
            diff_text=revert_diff(revert, target),
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
        confirmation_name: str,
    ) -> SnapshotChangePlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(SnapshotChangePlan, plan_id)
            if plan is None or plan.status != VmChangePlanStatus.PREVIEW:
                raise SnapshotChangeError("Snapshot revert plan is unavailable")
            if (
                plan.host_id != host_id
                or plan.vm_uuid != vm_uuid
                or plan.snapshot_name != snapshot_name
                or plan.operation != "revert"
            ):
                raise SnapshotChangeConflict("Snapshot revert plan scope does not match")
            vm = session.get(ResourceIndex, plan.vm_resource_id)
            if vm is None or not hmac.compare_digest(confirmation_name, vm.display_name):
                raise SnapshotChangeError("VM name confirmation is invalid")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = VmChangePlanStatus.EXPIRED
                raise SnapshotChangeError("Snapshot revert plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise SnapshotChangeError("Snapshot revert confirmation is invalid")
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
            raise SnapshotChangeError("Snapshot revert plan is not confirmed") from exc
        revert = SnapshotRevertInput.decode(plan.input_json)
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
                revert.snapshot_base.native_id,
                task_id,
            )
            return self._execute_locked(plan, revert, progress)
        finally:
            self.locks.release(
                plan.host_id,
                ResourceType.SNAPSHOT,
                revert.snapshot_base.native_id,
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
        revert: SnapshotRevertInput,
        progress: ChangeProgress | None,
    ) -> str:
        try:
            self.plans.mark_running(plan.id)
            _notify(progress, 1, "Refresh authoritative VM and Snapshot topology")
            self.shared._refresh_vm(revert)
            self.snapshots.run(plan.host_id)
            target, inventory = self.shared._target_and_inventory(revert)
            validate_revertable(revert, target, inventory)
            _notify(progress, 2, "Revert guest disk data to current Snapshot")
            _require_success(self._revert_command(revert))
            _notify(progress, 3, "Verify current Snapshot and preserved VM configuration")
            self.snapshots.run(plan.host_id)
            target, inventory = self.shared._target_and_inventory(revert)
            validate_revertable(revert, target, inventory)
            self.shared._refresh_vm(revert)
            self.plans.mark_succeeded(plan.id)
            return f"Snapshot reverted; vm={plan.vm_uuid}; name={plan.snapshot_name}"
        except Exception as exc:
            self.plans.mark_failed(plan.id, str(exc))
            raise

    def _revert_command(self, revert: SnapshotRevertInput) -> CommandResult:
        host = self.shared._host(revert.vm_base.host_id)
        return self.executor.run(
            revert.vm_base.host_id,
            CommandSpec(
                "virsh",
                (
                    "-c",
                    host.libvirt_uri,
                    "snapshot-revert",
                    revert.vm_base.native_id,
                    revert.name,
                ),
            ),
            sudo=host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS,
            timeout=3_600,
            env={"LC_ALL": "C"},
        )


def _notify(progress: ChangeProgress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)
