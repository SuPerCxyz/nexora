"""Preview, confirm, create, verify, and roll back storage pools."""

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
from nexora.remote.executor import RemoteExecutor
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.storage.contracts import StoragePoolCreateInput
from nexora.storage.models import StoragePoolChangePlan, StoragePoolPlanStatus
from nexora.storage.plan_store import StoragePoolPlanStore
from nexora.storage.plan_utils import creation_diff, error_message, matches_create, notify
from nexora.storage.remote_ops import StoragePoolRemoteCommands, require_success
from nexora.storage.xml import build_pool_xml
from nexora.tasks.locks import ResourceLockStore
from nexora.xml.document import LibvirtXmlDocument

PLAN_TTL = timedelta(minutes=10)
ChangeProgress = Callable[[int, str], None]


class StoragePoolError(RuntimeError):
    pass


class StoragePoolConflict(StoragePoolError):
    pass


@dataclass(frozen=True)
class StoragePoolPreview:
    plan: StoragePoolChangePlan
    confirmation_token: str


class StoragePoolService:
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        discovery: StorageDiscoveryService,
        locks: ResourceLockStore,
    ) -> None:
        self.database = database
        self.discovery = discovery
        self.locks = locks
        self.plan_store = StoragePoolPlanStore(database)
        self.commands = StoragePoolRemoteCommands(database, executor)

    def preview_create(self, create: StoragePoolCreateInput) -> StoragePoolPreview:
        create.validate()
        self.discovery.run(create.host_id)
        pool_uuid = str(uuid4())
        self._ensure_available(create, pool_uuid)
        proposed_xml = build_pool_xml(create, pool_uuid)
        self.commands.validate_xml(create.host_id, proposed_xml)
        document = LibvirtXmlDocument.parse(proposed_xml, expected_root="pool")
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = StoragePoolChangePlan(
            id=str(uuid4()),
            host_id=create.host_id,
            operation="create",
            pool_uuid=pool_uuid,
            pool_name=create.name,
            pool_type=create.pool_type,
            input_json=create.encode(),
            proposed_xml=proposed_xml,
            proposed_hash=document.fingerprint().digest,
            diff_text=creation_diff(proposed_xml),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=StoragePoolPlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return StoragePoolPreview(plan, token)

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
            if plan is None or plan.status != StoragePoolPlanStatus.PREVIEW:
                raise StoragePoolError("storage pool plan is unavailable")
            if plan.host_id != host_id or plan.pool_uuid != pool_uuid:
                raise StoragePoolConflict("storage pool plan scope does not match")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = StoragePoolPlanStatus.EXPIRED
                raise StoragePoolError("storage pool plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise StoragePoolError("storage pool confirmation is invalid")
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
            plan = self.plan_store.load_for_execution(plan_id)
        except ValueError as exc:
            raise StoragePoolError("storage pool plan is not confirmed") from exc
        create = StoragePoolCreateInput.decode(plan.input_json)
        self.locks.acquire(
            plan.host_id,
            ResourceType.STORAGE_POOL,
            plan.pool_uuid,
            task_id,
        )
        defined = False
        built = False
        try:
            self.plan_store.mark_running(plan.id)
            notify(progress, 1, "Refresh authoritative storage pool inventory")
            self.discovery.run(plan.host_id)
            existing = self._pool(plan.host_id, plan.pool_uuid)
            if existing is not None:
                if not matches_create(existing, create):
                    raise StoragePoolConflict("planned pool UUID now has different configuration")
                defined = True
                built = self._build_target(create, plan.pool_uuid)
                notify(progress, 3, "Apply requested pool state")
                self._apply_state(create, plan.pool_uuid, existing)
                notify(progress, 4, "Verify authoritative storage pool state")
                resource = self._verify(plan, create)
                self.plan_store.mark_succeeded(plan.id, resource.id)
                return f"storage pool already matches plan; uuid={plan.pool_uuid}"
            self._ensure_available(create, plan.pool_uuid)
            notify(progress, 2, "Define validated storage pool XML")
            require_success(
                self.commands.virsh(
                    plan.host_id,
                    ("pool-define", "/dev/stdin", "--validate"),
                    stdin=plan.proposed_xml,
                ),
                "libvirt rejected storage pool XML",
            )
            defined = True
            built = self._build_target(create, plan.pool_uuid)
            notify(progress, 3, "Apply requested pool state")
            self._apply_state(create, plan.pool_uuid)
            notify(progress, 4, "Verify authoritative storage pool state")
            resource = self._verify(plan, create)
            self.plan_store.mark_succeeded(plan.id, resource.id)
            return f"storage pool created; uuid={plan.pool_uuid}; type={plan.pool_type}"
        except Exception as exc:
            rollback_error = self._rollback(plan, create, built) if defined else None
            self.plan_store.mark_failed(plan.id, error_message(exc, rollback_error))
            raise
        finally:
            self.locks.release(
                plan.host_id,
                ResourceType.STORAGE_POOL,
                plan.pool_uuid,
                task_id,
            )

    def _apply_state(
        self,
        create: StoragePoolCreateInput,
        pool_uuid: str,
        existing: ResourceIndex | None = None,
    ) -> None:
        details = json.loads(existing.details_json) if existing is not None else {}
        if create.start and not details.get("active", False):
            require_success(
                self.commands.virsh(create.host_id, ("pool-start", pool_uuid)),
                "storage pool failed to start",
            )
        if create.autostart and not details.get("autostart", False):
            require_success(
                self.commands.virsh(create.host_id, ("pool-autostart", pool_uuid)),
                "storage pool autostart failed",
            )

    def _build_target(self, create: StoragePoolCreateInput, pool_uuid: str) -> bool:
        if self.commands.path_is_directory(create.host_id, create.target_path):
            return False
        require_success(
            self.commands.virsh(create.host_id, ("pool-build", pool_uuid)),
            "storage pool target build failed",
        )
        return True

    def _verify(
        self,
        plan: StoragePoolChangePlan,
        create: StoragePoolCreateInput,
    ) -> ResourceIndex:
        self.discovery.run(plan.host_id)
        resource = self._pool(plan.host_id, plan.pool_uuid)
        if resource is None or not matches_create(resource, create):
            raise StoragePoolError("created storage pool configuration verification failed")
        details = json.loads(resource.details_json)
        if bool(details["active"]) != create.start:
            raise StoragePoolError("created storage pool active state verification failed")
        if bool(details["autostart"]) != create.autostart:
            raise StoragePoolError("created storage pool autostart verification failed")
        return resource

    def _ensure_available(self, create: StoragePoolCreateInput, pool_uuid: str) -> None:
        with self.database.session() as session:
            resources = session.scalars(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == create.host_id,
                    ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                    ResourceIndex.status != ResourceStatus.MISSING,
                )
            )
            for resource in resources:
                details = json.loads(resource.details_json)
                collision = (
                    resource.native_id == pool_uuid
                    or resource.display_name == create.name
                    or details.get("target_path") == create.target_path
                )
                if collision:
                    raise StoragePoolConflict("storage pool name, UUID, or target already exists")

    def _pool(self, host_id: str, pool_uuid: str) -> ResourceIndex | None:
        with self.database.session() as session:
            return session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                    ResourceIndex.native_id == pool_uuid,
                    ResourceIndex.status != ResourceStatus.MISSING,
                )
            )

    def _rollback(
        self,
        plan: StoragePoolChangePlan,
        create: StoragePoolCreateInput,
        built: bool,
    ) -> str | None:
        errors: list[str] = []
        destroy = self.commands.virsh(plan.host_id, ("pool-destroy", plan.pool_uuid))
        if destroy.exit_code not in {0, 1}:
            errors.append("pool destroy failed")
        undefine = self.commands.virsh(plan.host_id, ("pool-undefine", plan.pool_uuid))
        if undefine.exit_code != 0:
            errors.append("pool undefine failed")
        self.discovery.run(plan.host_id)
        if self._pool(plan.host_id, plan.pool_uuid) is not None:
            errors.append("pool definition remains after rollback")
        if built:
            try:
                self.commands.remove_empty_directory(plan.host_id, create.target_path)
            except RuntimeError as exc:
                errors.append(str(exc))
        return "; ".join(errors) or None
