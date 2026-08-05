"""Preview, confirm, delete, verify, and roll back storage pool definitions."""

import difflib
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
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.storage.models import StoragePoolChangePlan, StoragePoolPlanStatus
from nexora.storage.plan_store import StoragePoolPlanStore
from nexora.storage.plan_utils import error_message, notify
from nexora.storage.remote_ops import StoragePoolRemoteCommands, require_success
from nexora.storage.service import StoragePoolConflict, StoragePoolError
from nexora.storage.usage import StoragePoolInUseError, StoragePoolUsageGuard
from nexora.tasks.locks import ResourceLockStore

PLAN_TTL = timedelta(minutes=10)
ChangeProgress = Callable[[int, str], None]


@dataclass(frozen=True)
class StoragePoolDeletePreview:
    plan: StoragePoolChangePlan
    confirmation_token: str


class StoragePoolDeleteService:
    def __init__(
        self,
        database: Database,
        discovery: StorageDiscoveryService,
        domains: DomainDiscoveryService,
        store: ResourceIndexStore,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
        commands: StoragePoolRemoteCommands,
    ) -> None:
        self.database = database
        self.discovery = discovery
        self.domains = domains
        self.store = store
        self.guard = guard
        self.locks = locks
        self.commands = commands
        self.plan_store = StoragePoolPlanStore(database)
        self.usage = StoragePoolUsageGuard(database)

    def preview(self, base: ResourceBaseVersion) -> StoragePoolDeletePreview:
        observation = self.discovery.read_pool(base.host_id, base.native_id)
        self.domains.run(base.host_id)
        indexed = self.store.refresh_one(
            base.host_id,
            ResourceType.STORAGE_POOL,
            observation,
        )
        self.guard.verify(base)
        details = observation.details
        if details.get("pool_type") not in {"dir", "netfs"}:
            raise StoragePoolConflict("storage pool type is read-only")
        if not bool(details.get("persistent")):
            raise StoragePoolConflict("transient storage pool cannot be undefined")
        self._ensure_not_in_use(base.host_id, indexed.display_name, details.get("target_path"))
        original_xml = observation.documents.get("pool_xml")
        if original_xml is None or observation.persistent_hash is None:
            raise StoragePoolConflict("persistent storage pool XML is unavailable")
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = StoragePoolChangePlan(
            id=str(uuid4()),
            host_id=base.host_id,
            operation="delete",
            pool_resource_id=indexed.id,
            pool_uuid=base.native_id,
            pool_name=indexed.display_name,
            pool_type=str(details["pool_type"]),
            base_generation=base.generation,
            base_persistent_hash=observation.persistent_hash,
            input_json=json.dumps(
                {
                    "active": bool(details.get("active")),
                    "autostart": bool(details.get("autostart")),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            current_xml=original_xml,
            diff_text=_deletion_diff(original_xml),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=StoragePoolPlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return StoragePoolDeletePreview(plan, token)

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        pool_uuid: str,
    ) -> StoragePoolChangePlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(StoragePoolChangePlan, plan_id)
            if (
                plan is None
                or plan.operation != "delete"
                or plan.status != StoragePoolPlanStatus.PREVIEW
            ):
                raise StoragePoolError("storage pool deletion plan is unavailable")
            if plan.host_id != host_id or plan.pool_uuid != pool_uuid:
                raise StoragePoolConflict("storage pool deletion plan scope does not match")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = StoragePoolPlanStatus.EXPIRED
                raise StoragePoolError("storage pool deletion plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise StoragePoolError("storage pool deletion confirmation is invalid")
            plan.status = StoragePoolPlanStatus.CONFIRMED
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
            plan = self.plan_store.load_for_execution(plan_id)
        except ValueError as exc:
            raise StoragePoolError("storage pool deletion plan is not confirmed") from exc
        was_recovery = plan.status == StoragePoolPlanStatus.RUNNING
        self.locks.acquire(
            plan.host_id,
            ResourceType.STORAGE_POOL,
            plan.pool_uuid,
            task_id,
        )
        undefined = False
        try:
            self.plan_store.mark_running(plan.id)
            notify(progress, 1, "Refresh authoritative storage pool state")
            self.discovery.run(plan.host_id)
            self.domains.run(plan.host_id)
            resource = self._pool(plan.pool_resource_id)
            if resource is None or resource.status == ResourceStatus.MISSING:
                if not was_recovery:
                    raise StoragePoolConflict("storage pool disappeared after preview")
                self.plan_store.mark_succeeded(plan.id, plan.pool_resource_id or "")
                return f"storage pool definition already absent; uuid={plan.pool_uuid}"
            observation = self.discovery.read_pool(plan.host_id, plan.pool_uuid)
            self.store.refresh_one(plan.host_id, ResourceType.STORAGE_POOL, observation)
            self.guard.verify(_base(plan))
            if observation.persistent_hash != plan.base_persistent_hash:
                raise StoragePoolConflict("storage pool XML changed after preview")
            details = observation.details
            self._ensure_not_in_use(plan.host_id, resource.display_name, details.get("target_path"))
            notify(progress, 2, "Stop storage pool without deleting target data")
            if bool(details.get("active")):
                require_success(
                    self.commands.virsh(
                        plan.host_id,
                        ("pool-destroy", plan.pool_uuid),
                    ),
                    "storage pool failed to stop",
                )
            notify(progress, 3, "Undefine storage pool without deleting target data")
            require_success(
                self.commands.virsh(plan.host_id, ("pool-undefine", plan.pool_uuid)),
                "storage pool failed to undefine",
            )
            undefined = True
            notify(progress, 4, "Verify definition removal and preserved target scope")
            self.discovery.run(plan.host_id)
            final = self._pool(plan.pool_resource_id)
            if final is None or final.status != ResourceStatus.MISSING:
                raise StoragePoolError("storage pool definition removal verification failed")
            self.plan_store.mark_succeeded(plan.id, final.id)
            return f"storage pool definition removed; data_preserved=true; uuid={plan.pool_uuid}"
        except Exception as exc:
            rollback = self._rollback(plan) if undefined else None
            self.plan_store.mark_failed(plan.id, error_message(exc, rollback))
            raise
        finally:
            self.locks.release(
                plan.host_id,
                ResourceType.STORAGE_POOL,
                plan.pool_uuid,
                task_id,
            )

    def _rollback(self, plan: StoragePoolChangePlan) -> str | None:
        if plan.current_xml is None:
            return "original pool XML is unavailable"
        try:
            require_success(
                self.commands.virsh(
                    plan.host_id,
                    ("pool-define", "/dev/stdin", "--validate"),
                    stdin=plan.current_xml,
                ),
                "storage pool rollback define failed",
            )
            state = json.loads(plan.input_json)
            if state["active"]:
                require_success(
                    self.commands.virsh(plan.host_id, ("pool-start", plan.pool_uuid)),
                    "storage pool rollback start failed",
                )
            if state["autostart"]:
                require_success(
                    self.commands.virsh(plan.host_id, ("pool-autostart", plan.pool_uuid)),
                    "storage pool rollback autostart failed",
                )
            return None
        except Exception as exc:
            return str(exc)

    def _pool(self, resource_id: str | None) -> ResourceIndex | None:
        if resource_id is None:
            return None
        with self.database.session() as session:
            return session.scalar(select(ResourceIndex).where(ResourceIndex.id == resource_id))

    def _ensure_not_in_use(
        self,
        host_id: str,
        pool_name: str,
        target_path: object,
    ) -> None:
        try:
            self.usage.ensure_not_in_use(host_id, pool_name, target_path)
        except StoragePoolInUseError as exc:
            raise StoragePoolConflict(str(exc)) from exc


def _base(plan: StoragePoolChangePlan) -> ResourceBaseVersion:
    return ResourceBaseVersion(
        plan.pool_resource_id or "",
        plan.host_id,
        ResourceType.STORAGE_POOL,
        plan.pool_uuid,
        plan.base_generation or 0,
        plan.base_persistent_hash,
        None,
    )


def _deletion_diff(content: bytes) -> str:
    lines = content.decode().splitlines(keepends=True)
    return "".join(difflib.unified_diff(lines, [], fromfile="pool.xml", tofile="/dev/null"))
