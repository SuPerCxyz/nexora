"""Preview, confirm, create, and verify storage volumes."""

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
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.storage.models import StoragePoolPlanStatus
from nexora.storage.plan_utils import creation_diff, notify
from nexora.storage.volume_contracts import StorageVolumeCreateInput
from nexora.storage.volume_models import StorageVolumeChangePlan
from nexora.storage.volume_plan_store import StorageVolumePlanStore
from nexora.storage.volume_remote import StorageVolumeRemoteCommands
from nexora.storage.volume_xml import build_volume_xml
from nexora.tasks.locks import ResourceLockStore

PLAN_TTL = timedelta(minutes=10)
ChangeProgress = Callable[[int, str], None]


class StorageVolumeError(RuntimeError):
    pass


class StorageVolumeConflict(StorageVolumeError):
    pass


@dataclass(frozen=True)
class StorageVolumePreview:
    plan: StorageVolumeChangePlan
    confirmation_token: str


class StorageVolumeService:
    def __init__(
        self,
        database: Database,
        discovery: StorageDiscoveryService,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
        commands: StorageVolumeRemoteCommands,
    ) -> None:
        self.database = database
        self.discovery = discovery
        self.guard = guard
        self.locks = locks
        self.commands = commands
        self.plans = StorageVolumePlanStore(database)

    def preview_create(self, create: StorageVolumeCreateInput) -> StorageVolumePreview:
        create.validate()
        self.discovery.run(create.host_id)
        self._verify_pool(create)
        if self._volume(create.host_id, create.pool_uuid, create.name) is not None:
            raise StorageVolumeConflict("storage volume name already exists")
        proposed_xml = build_volume_xml(create)
        self.commands.validate_xml(create.host_id, proposed_xml)
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = StorageVolumeChangePlan(
            id=str(uuid4()),
            host_id=create.host_id,
            operation="create",
            pool_resource_id=create.pool_resource_id,
            pool_uuid=create.pool_uuid,
            volume_name=create.name,
            volume_format=create.volume_format,
            pool_generation=create.pool_generation,
            pool_hash=create.pool_hash,
            input_json=create.encode(),
            proposed_xml=proposed_xml,
            diff_text=creation_diff(proposed_xml),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=StoragePoolPlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return StorageVolumePreview(plan, token)

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        pool_uuid: str,
    ) -> StorageVolumeChangePlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(StorageVolumeChangePlan, plan_id)
            if plan is None or plan.status != StoragePoolPlanStatus.PREVIEW:
                raise StorageVolumeError("storage volume plan is unavailable")
            if plan.host_id != host_id or plan.pool_uuid != pool_uuid:
                raise StorageVolumeConflict("storage volume plan scope does not match")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = StoragePoolPlanStatus.EXPIRED
                raise StorageVolumeError("storage volume plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise StorageVolumeError("storage volume confirmation is invalid")
            plan.status = StoragePoolPlanStatus.CONFIRMED
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
            plan = self.plans.load_for_execution(plan_id)
        except ValueError as exc:
            raise StorageVolumeError("storage volume plan is not confirmed") from exc
        was_recovery = plan.status == StoragePoolPlanStatus.RUNNING
        create = StorageVolumeCreateInput.decode(plan.input_json)
        self.locks.acquire(
            plan.host_id,
            ResourceType.STORAGE_POOL,
            plan.pool_uuid,
            task_id,
        )
        try:
            self.plans.mark_running(plan.id)
            notify(progress, 1, "Refresh authoritative pool and volume inventory")
            self.discovery.run(plan.host_id)
            self._verify_pool(create)
            existing = self._volume(plan.host_id, plan.pool_uuid, plan.volume_name)
            if existing is not None:
                if not was_recovery or not _matches(existing, create):
                    raise StorageVolumeConflict("storage volume appeared after preview")
                self.plans.mark_succeeded(plan.id, existing.id, existing.native_id)
                return f"storage volume already matches plan; name={plan.volume_name}"
            notify(progress, 2, "Create validated storage volume without overwrite")
            result = self.commands.virsh(
                plan.host_id,
                ("vol-create", plan.pool_uuid, "/dev/stdin"),
                stdin=plan.proposed_xml,
            )
            _require_success(result)
            notify(progress, 3, "Verify authoritative storage volume identity and capacity")
            self.discovery.run(plan.host_id)
            final = self._volume(plan.host_id, plan.pool_uuid, plan.volume_name)
            if final is None or not _matches(final, create):
                raise StorageVolumeError("created storage volume verification failed")
            self.plans.mark_succeeded(plan.id, final.id, final.native_id)
            return f"storage volume created; name={plan.volume_name}; format={plan.volume_format}"
        except Exception as exc:
            self.plans.mark_failed(plan.id, str(exc))
            raise
        finally:
            self.locks.release(
                plan.host_id,
                ResourceType.STORAGE_POOL,
                plan.pool_uuid,
                task_id,
            )

    def _verify_pool(self, create: StorageVolumeCreateInput) -> ResourceIndex:
        with self.database.session() as session:
            pool = session.get(ResourceIndex, create.pool_resource_id)
            if pool is None:
                raise StorageVolumeConflict("storage pool no longer exists")
            details = json.loads(pool.details_json)
            if (
                pool.host_id != create.host_id
                or pool.resource_type != ResourceType.STORAGE_POOL
                or pool.native_id != create.pool_uuid
                or pool.status != ResourceStatus.MANAGED
                or details.get("pool_type") not in {"dir", "netfs"}
                or not bool(details.get("active"))
            ):
                raise StorageVolumeConflict("storage pool is not writable and active")
        self.guard.verify(
            ResourceBaseVersion(
                create.pool_resource_id,
                create.host_id,
                ResourceType.STORAGE_POOL,
                create.pool_uuid,
                create.pool_generation,
                create.pool_hash,
                None,
            )
        )
        return pool

    def _volume(
        self,
        host_id: str,
        pool_uuid: str,
        name: str,
    ) -> ResourceIndex | None:
        with self.database.session() as session:
            return session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.STORAGE_VOLUME,
                    ResourceIndex.parent_native_id == pool_uuid,
                    ResourceIndex.display_name == name,
                    ResourceIndex.status != ResourceStatus.MISSING,
                )
            )


def _matches(resource: ResourceIndex, create: StorageVolumeCreateInput) -> bool:
    details: dict[str, object] = json.loads(resource.details_json)
    return (
        details.get("format") == create.volume_format
        and details.get("capacity_bytes") == create.capacity_bytes
    )


def _require_success(result: CommandResult) -> None:
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    ):
        raise StorageVolumeError("storage volume creation failed")
