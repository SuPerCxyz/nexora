"""Preview, confirm, create, and verify internal VM Snapshots."""

import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.conflicts import ResourceWriteGuard
from nexora.resources.contracts import ResourceObservation
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.snapshot_discovery import SnapshotDiscoveryService
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.snapshot_contracts import SnapshotCreateInput
from nexora.vms.snapshot_errors import SnapshotChangeConflict, SnapshotChangeError
from nexora.vms.snapshot_models import SnapshotChangePlan
from nexora.vms.snapshot_plan_store import SnapshotPlanStore
from nexora.vms.snapshot_validation import (
    creation_diff,
    snapshot_native_id,
    supported_disks,
    verify_created,
)

PLAN_TTL = timedelta(minutes=10)
ChangeProgress = Callable[[int, str], None]


@dataclass(frozen=True)
class SnapshotPreview:
    plan: SnapshotChangePlan
    confirmation_token: str


class SnapshotService:
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        domains: DomainDiscoveryService,
        snapshots: SnapshotDiscoveryService,
        store: ResourceIndexStore,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
    ) -> None:
        self.database = database
        self.executor = executor
        self.domains = domains
        self.snapshots = snapshots
        self.store = store
        self.guard = guard
        self.locks = locks
        self.plans = SnapshotPlanStore(database)

    def preview_create(self, create: SnapshotCreateInput) -> SnapshotPreview:
        create.validate()
        observation = self._refresh_vm(create)
        disks = supported_disks(observation)
        self.snapshots.run(create.vm_base.host_id)
        if self._snapshot(create.vm_base.host_id, create.vm_base.native_id, create.name):
            raise SnapshotChangeConflict("Snapshot name already exists")
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = SnapshotChangePlan(
            id=str(uuid4()),
            host_id=create.vm_base.host_id,
            operation="create",
            vm_resource_id=create.vm_base.resource_id,
            vm_uuid=create.vm_base.native_id,
            snapshot_name=create.name,
            vm_generation=create.vm_base.generation,
            vm_hash=create.vm_base.persistent_hash,
            input_json=create.encode(),
            diff_text=creation_diff(create, disks),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=VmChangePlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return SnapshotPreview(plan, token)

    def confirm_create(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
    ) -> SnapshotChangePlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(SnapshotChangePlan, plan_id)
            if plan is None or plan.status != VmChangePlanStatus.PREVIEW:
                raise SnapshotChangeError("Snapshot plan is unavailable")
            if plan.host_id != host_id or plan.vm_uuid != vm_uuid or plan.operation != "create":
                raise SnapshotChangeConflict("Snapshot plan scope does not match")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = VmChangePlanStatus.EXPIRED
                raise SnapshotChangeError("Snapshot plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise SnapshotChangeError("Snapshot confirmation is invalid")
            plan.status = VmChangePlanStatus.CONFIRMED
            plan.confirmed_at = now
            return plan

    def execute_create(
        self,
        plan_id: str,
        *,
        task_id: str,
        progress: ChangeProgress | None = None,
    ) -> str:
        try:
            plan = self.plans.load_confirmed(plan_id)
        except ValueError as exc:
            raise SnapshotChangeError("Snapshot plan is not confirmed") from exc
        create = SnapshotCreateInput.decode(plan.input_json)
        native_id = snapshot_native_id(plan.vm_uuid, plan.snapshot_name)
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
                native_id,
                task_id,
            )
            return self._execute_locked(plan, create, progress)
        finally:
            self.locks.release(
                plan.host_id,
                ResourceType.SNAPSHOT,
                native_id,
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
        create: SnapshotCreateInput,
        progress: ChangeProgress | None,
    ) -> str:
        try:
            self.plans.mark_running(plan.id)
            _notify(progress, 1, "Refresh authoritative VM and Snapshot inventory")
            self._refresh_vm(create)
            self.snapshots.run(plan.host_id)
            if self._snapshot(plan.host_id, plan.vm_uuid, plan.snapshot_name):
                raise SnapshotChangeConflict("Snapshot appeared after preview")
            _notify(progress, 2, "Create atomic internal disk Snapshot")
            _require_success(self._create_command(create))
            _notify(progress, 3, "Verify authoritative Snapshot XML and disk modes")
            self.snapshots.run(plan.host_id)
            snapshot = self._snapshot(plan.host_id, plan.vm_uuid, plan.snapshot_name)
            verify_created(snapshot)
            self._verify_vm_hash(create)
            self.plans.mark_succeeded(plan.id)
            return f"Snapshot created; vm={plan.vm_uuid}; name={plan.snapshot_name}"
        except Exception as exc:
            self.plans.mark_failed(plan.id, str(exc))
            raise

    def _refresh_vm(self, create: SnapshotCreateInput) -> ResourceObservation:
        observation = self.domains.read_one(
            create.vm_base.host_id,
            create.vm_base.native_id,
        )
        self.store.refresh_one(
            create.vm_base.host_id,
            ResourceType.VIRTUAL_MACHINE,
            observation,
        )
        self.guard.verify(create.vm_base)
        if observation.persistent_hash is None:
            raise SnapshotChangeConflict("Snapshot creation requires a persistent VM")
        if bool(observation.details.get("active")):
            raise SnapshotChangeConflict("Snapshot creation requires a shut-off VM")
        return observation

    def _verify_vm_hash(self, create: SnapshotCreateInput) -> None:
        observation = self.domains.read_one(
            create.vm_base.host_id,
            create.vm_base.native_id,
        )
        if observation.persistent_hash != create.vm_base.persistent_hash:
            raise SnapshotChangeConflict("VM XML changed during Snapshot creation")
        self.store.refresh_one(
            create.vm_base.host_id,
            ResourceType.VIRTUAL_MACHINE,
            observation,
        )

    def _snapshot(
        self,
        host_id: str,
        vm_uuid: str,
        name: str,
    ) -> ResourceIndex | None:
        with self.database.session() as session:
            return session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.SNAPSHOT,
                    ResourceIndex.parent_native_id == vm_uuid,
                    ResourceIndex.display_name == name,
                    ResourceIndex.status != ResourceStatus.MISSING,
                )
            )

    def _create_command(self, create: SnapshotCreateInput) -> CommandResult:
        host = self._host(create.vm_base.host_id)
        return self.executor.run(
            create.vm_base.host_id,
            CommandSpec(
                "virsh",
                (
                    "-c",
                    host.libvirt_uri,
                    "snapshot-create-as",
                    create.vm_base.native_id,
                    create.name,
                    create.description,
                    "--atomic",
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


def _require_success(result: CommandResult) -> None:
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    ):
        raise SnapshotChangeError("libvirt Snapshot creation failed")


def _notify(progress: ChangeProgress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)
