"""Preview, confirm, execute, and verify storage volume mutations."""

import difflib
import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from nexora.db import Database
from nexora.resources.conflicts import ResourceWriteGuard
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.storage.models import StoragePoolPlanStatus
from nexora.storage.volume_authority import StorageVolumeAuthority
from nexora.storage.volume_contracts import StorageVolumeMutationInput
from nexora.storage.volume_models import StorageVolumeChangePlan
from nexora.storage.volume_mutation_executor import StorageVolumeMutationExecutor
from nexora.storage.volume_plan_store import StorageVolumePlanStore
from nexora.storage.volume_remote import StorageVolumeRemoteCommands
from nexora.storage.volume_service import (
    StorageVolumeConflict,
    StorageVolumeError,
    StorageVolumePreview,
)
from nexora.storage.volume_xml import resize_volume_xml
from nexora.tasks.locks import ResourceLockStore

PLAN_TTL = timedelta(minutes=10)
ChangeProgress = Callable[[int, str], None]


class StorageVolumeMutationService:
    def __init__(
        self,
        database: Database,
        storage_discovery: StorageDiscoveryService,
        domain_discovery: DomainDiscoveryService,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
        commands: StorageVolumeRemoteCommands,
    ) -> None:
        self.database = database
        self.commands = commands
        self.plans = StorageVolumePlanStore(database)
        self.authority = StorageVolumeAuthority(
            database,
            storage_discovery,
            domain_discovery,
            guard,
        )
        self.executor = StorageVolumeMutationExecutor(
            self.authority,
            locks,
            commands,
            self.plans,
        )

    def preview_resize(
        self,
        change: StorageVolumeMutationInput,
    ) -> StorageVolumePreview:
        change.validate("resize")
        verified = self.authority.refresh_and_verify(change, operation="resize")
        proposed = resize_volume_xml(
            verified.current_xml,
            _required_target(change),
        )
        self.commands.validate_xml(change.host_id, proposed)
        return self._persist_preview(
            change,
            operation="resize",
            current_xml=verified.current_xml,
            proposed_xml=proposed,
            volume_format=str(verified.details["format"]),
        )

    def preview_delete(
        self,
        change: StorageVolumeMutationInput,
    ) -> StorageVolumePreview:
        change.validate("delete")
        verified = self.authority.refresh_and_verify(change, operation="delete")
        return self._persist_preview(
            change,
            operation="delete",
            current_xml=verified.current_xml,
            proposed_xml=None,
            volume_format=str(verified.details["format"]),
        )

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

    def execute(
        self,
        plan_id: str,
        *,
        task_id: str,
        progress: ChangeProgress | None = None,
    ) -> str:
        return self.executor.execute(
            plan_id,
            task_id=task_id,
            progress=progress,
        )

    def _persist_preview(
        self,
        change: StorageVolumeMutationInput,
        *,
        operation: str,
        current_xml: bytes,
        proposed_xml: bytes | None,
        volume_format: str,
    ) -> StorageVolumePreview:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = StorageVolumeChangePlan(
            id=str(uuid4()),
            host_id=change.host_id,
            operation=operation,
            pool_resource_id=change.pool_resource_id,
            pool_uuid=change.pool_uuid,
            volume_resource_id=change.volume_resource_id,
            volume_native_id=change.volume_native_id,
            volume_name=change.volume_name,
            volume_format=volume_format,
            pool_generation=change.pool_generation,
            pool_hash=change.pool_hash,
            volume_generation=change.volume_generation,
            volume_hash=change.volume_hash,
            input_json=change.encode(),
            current_xml=current_xml,
            proposed_xml=proposed_xml,
            diff_text=_xml_diff(current_xml, proposed_xml),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=StoragePoolPlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return StorageVolumePreview(plan, token)


def _required_target(change: StorageVolumeMutationInput) -> int:
    target = change.target_capacity_bytes
    if target is None:
        raise StorageVolumeError("storage volume resize target is missing")
    return target


def _xml_diff(current: bytes, proposed: bytes | None) -> str:
    before = current.decode().splitlines(keepends=True)
    after = [] if proposed is None else proposed.decode().splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            before,
            after,
            fromfile="current-volume.xml",
            tofile="/dev/null" if proposed is None else "proposed-volume.xml",
        )
    )
