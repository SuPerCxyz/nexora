"""Preview, confirm, execute, and audit a fail-closed host removal."""

import hmac
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from nexora.db import Database
from nexora.hosts.models import Host, HostFingerprint, HostStatus, SudoMode
from nexora.hosts.removal_inventory import RemoteCleanupInventory, RemoteCleanupService
from nexora.hosts.removal_models import (
    HostRemovalMode,
    HostRemovalPlan,
    HostRemovalPlanStatus,
    HostRemovalTombstone,
)
from nexora.remote.host_key_store import HostKeyStore
from nexora.tasks.models import Task
from nexora.tasks.read_service import ACTIVE_TASK_STATUSES

PLAN_TTL = timedelta(minutes=10)
RemovalProgress = Callable[[int, str], None]


class HostRemovalError(RuntimeError):
    pass


class HostRemovalConflict(HostRemovalError):
    pass


@dataclass(frozen=True)
class HostRemovalPreview:
    plan: HostRemovalPlan
    confirmation_token: str
    inventory: RemoteCleanupInventory


class HostRemovalService:
    def __init__(
        self,
        database: Database,
        cleanup: RemoteCleanupService,
        host_keys: HostKeyStore,
    ) -> None:
        self.database = database
        self.cleanup = cleanup
        self.host_keys = host_keys

    def preview(self, host_id: str, mode: HostRemovalMode) -> HostRemovalPreview:
        host = self._host(host_id)
        inventory = (
            self.cleanup.discover(host_id, sudo=_uses_sudo(host))
            if mode == HostRemovalMode.CLEAN_TEMPORARY
            else RemoteCleanupInventory((), ())
        )
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = HostRemovalPlan(
            id=str(uuid4()),
            host_id=host.id,
            host_name=host.name,
            mode=mode,
            original_host_status=host.status,
            remote_paths_json=_json(inventory.paths),
            remote_units_json=_json(inventory.units),
            warnings_json=_json(inventory.warnings),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=HostRemovalPlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return HostRemovalPreview(plan, token, inventory)

    def confirm(
        self,
        plan_id: str,
        token: str,
        confirmation_name: str,
        expected_host_id: str | None = None,
    ) -> HostRemovalPlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(HostRemovalPlan, plan_id)
            if plan is None or plan.status != HostRemovalPlanStatus.PREVIEW:
                raise HostRemovalError("removal plan is unavailable")
            if expected_host_id is not None and plan.host_id != expected_host_id:
                raise HostRemovalConflict("removal plan scope does not match")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = HostRemovalPlanStatus.EXPIRED
                raise HostRemovalError("removal plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise HostRemovalError("removal confirmation is invalid")
            if not hmac.compare_digest(confirmation_name, plan.host_name):
                raise HostRemovalError("host name confirmation does not match")
            host = session.get(Host, plan.host_id)
            if host is None or host.status != plan.original_host_status:
                raise HostRemovalConflict("host state changed after removal preview")
            self._reject_active_tasks(session, host.id)
            host.status = HostStatus.REMOVAL_PENDING
            host.updated_at = now
            plan.status = HostRemovalPlanStatus.CONFIRMED
            plan.confirmed_at = now
            return plan

    def execute(
        self,
        plan_id: str,
        *,
        task_id: str,
        progress: RemovalProgress | None = None,
    ) -> str:
        plan, host = self._start(plan_id, task_id)
        try:
            _notify(progress, 1, "Verify confirmed removal plan")
            inventory = _plan_inventory(plan)
            try:
                mode = HostRemovalMode(plan.mode)
            except ValueError as exc:
                raise HostRemovalError("stored removal mode is invalid") from exc
            _notify(progress, 2, "Clean Nexora temporary entities")
            if mode == HostRemovalMode.CLEAN_TEMPORARY:
                current = self.cleanup.discover(host.id, sudo=_uses_sudo(host))
                if current.paths != inventory.paths or current.units != inventory.units:
                    raise HostRemovalConflict(
                        "remote temporary inventory changed after confirmation"
                    )
                self.cleanup.cleanup(host.id, current, sudo=_uses_sudo(host))
                remaining = self.cleanup.discover(host.id, sudo=_uses_sudo(host))
                if remaining.paths or remaining.units:
                    raise HostRemovalError("remote temporary cleanup verification failed")
            _notify(progress, 3, "Remove local management records")
            summary = self._remove_local(plan.id, host.id, inventory)
            return summary
        except Exception as exc:
            self._mark_failed(plan.id, host.id, str(exc))
            raise

    def _start(self, plan_id: str, task_id: str) -> tuple[HostRemovalPlan, Host]:
        with self.database.session() as session:
            plan = session.get(HostRemovalPlan, plan_id)
            if plan is None or plan.status != HostRemovalPlanStatus.CONFIRMED:
                raise HostRemovalError("removal plan is not confirmed")
            host = session.get(Host, plan.host_id)
            if host is None or host.status != HostStatus.REMOVAL_PENDING:
                raise HostRemovalConflict("host is not pending removal")
            self._reject_active_tasks(session, host.id, ignored_task_id=task_id)
            plan.status = HostRemovalPlanStatus.RUNNING
            return plan, host

    def _remove_local(
        self,
        plan_id: str,
        host_id: str,
        inventory: RemoteCleanupInventory,
    ) -> str:
        self.host_keys.delete(host_id)
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(HostRemovalPlan, plan_id)
            host = session.get(Host, host_id)
            if plan is None or host is None:
                raise HostRemovalConflict("host removal state disappeared")
            fingerprints = list(
                session.scalars(
                    select(HostFingerprint.fingerprint).where(HostFingerprint.host_id == host_id)
                )
            )
            summary = {
                "remote_paths_removed": len(inventory.paths),
                "remote_units_removed": len(inventory.units),
                "business_resources_removed": 0,
            }
            session.add(
                HostRemovalTombstone(
                    id=str(uuid4()),
                    original_host_id=host.id,
                    host_name=host.name,
                    address=host.address,
                    ssh_port=host.ssh_port,
                    fingerprints_json=_json(fingerprints),
                    mode=plan.mode,
                    cleanup_summary_json=_json(summary),
                    removed_at=now,
                )
            )
            session.delete(host)
            plan.status = HostRemovalPlanStatus.SUCCEEDED
            plan.finished_at = now
        return f"host removed; business_resources_removed=0; paths={len(inventory.paths)}"

    def _mark_failed(self, plan_id: str, host_id: str, error: str) -> None:
        with self.database.session() as session:
            plan = session.get(HostRemovalPlan, plan_id)
            host = session.get(Host, host_id)
            if plan is not None:
                plan.status = HostRemovalPlanStatus.FAILED
                plan.finished_at = datetime.now(UTC)
                plan.error_message = error[:2_048]
            if host is not None and host.status == HostStatus.REMOVAL_PENDING:
                host.status = plan.original_host_status if plan is not None else HostStatus.DEGRADED

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise HostRemovalError("host not found")
            if host.status == HostStatus.REMOVAL_PENDING:
                raise HostRemovalConflict("host already has a confirmed removal")
            return host

    def _reject_active_tasks(
        self,
        session: Session,
        host_id: str,
        *,
        ignored_task_id: str | None = None,
    ) -> None:
        statement = select(Task.id).where(
            Task.host_id == host_id,
            Task.status.in_(ACTIVE_TASK_STATUSES),
        )
        if ignored_task_id is not None:
            statement = statement.where(Task.id != ignored_task_id)
        if session.scalar(statement.limit(1)) is not None:
            raise HostRemovalConflict("host has an active task")


def _uses_sudo(host: Host) -> bool:
    return host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _plan_inventory(plan: HostRemovalPlan) -> RemoteCleanupInventory:
    try:
        paths = _string_list(json.loads(plan.remote_paths_json))
        units = _string_list(json.loads(plan.remote_units_json))
        warnings = _string_list(json.loads(plan.warnings_json))
    except (TypeError, json.JSONDecodeError) as exc:
        raise HostRemovalError("stored removal inventory is invalid") from exc
    return RemoteCleanupInventory(paths, units, warnings)


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError("expected string list")
    return tuple(value)


def _notify(progress: RemovalProgress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)
