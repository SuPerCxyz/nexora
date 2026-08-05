"""Preview, confirm, apply, verify, and roll back VM CPU XML changes."""

import hmac
import json
import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.contracts import ResourceObservation
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceType
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlan, VmChangePlanStatus
from nexora.vms.change_store import VmChangePlanStore
from nexora.xml import CpuTopologyChange, LibvirtXmlDocument, apply_cpu_topology
from nexora.xml.diff import xml_diff

PLAN_TTL = timedelta(minutes=10)
ChangeProgress = Callable[[int, str], None]


class VmChangeError(RuntimeError):
    pass


class VmChangeConflict(VmChangeError):
    pass


@dataclass(frozen=True)
class VmChangePreview:
    plan: VmChangePlan
    confirmation_token: str


class VmCpuChangeService:
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        discovery: DomainDiscoveryService,
        store: ResourceIndexStore,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
    ) -> None:
        self.database = database
        self.executor = executor
        self.discovery = discovery
        self.store = store
        self.guard = guard
        self.locks = locks
        self.plan_store = VmChangePlanStore(database)

    def preview(
        self,
        base: ResourceBaseVersion,
        change: CpuTopologyChange,
    ) -> VmChangePreview:
        change.validate()
        current, original_xml, original_hash = self._current_persistent(base)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_cpu_topology(proposed, change)
        return self._create_preview(
            base,
            "cpu_topology",
            asdict(change),
            current,
            proposed,
            original_xml,
            original_hash,
        )

    def _current_persistent(
        self,
        base: ResourceBaseVersion,
    ) -> tuple[LibvirtXmlDocument, bytes, str]:
        observation = self.discovery.read_one(base.host_id, base.native_id)
        self.store.refresh_one(base.host_id, ResourceType.VIRTUAL_MACHINE, observation)
        self.guard.verify(base)
        original_xml = observation.documents.get("persistent_xml")
        if original_xml is None or observation.persistent_hash is None:
            raise VmChangeConflict("configuration requires a persistent VM")
        current = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        return current, original_xml, observation.persistent_hash

    def _create_preview(
        self,
        base: ResourceBaseVersion,
        change_type: str,
        change_input: dict[str, object],
        current: LibvirtXmlDocument,
        proposed: LibvirtXmlDocument,
        original_xml: bytes,
        original_hash: str,
    ) -> VmChangePreview:
        proposed_hash = proposed.fingerprint().digest
        if proposed_hash == original_hash:
            raise VmChangeConflict("proposed VM configuration has no changes")
        proposed_xml = proposed.serialize()
        self._validate_remote(base.host_id, proposed_xml)
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = VmChangePlan(
            id=str(uuid4()),
            host_id=base.host_id,
            resource_index_id=base.resource_id,
            vm_uuid=base.native_id,
            change_type=change_type,
            base_generation=base.generation,
            base_persistent_hash=original_hash,
            original_xml=original_xml,
            proposed_xml=proposed_xml,
            proposed_persistent_hash=proposed_hash,
            change_input_json=json.dumps(change_input, sort_keys=True, separators=(",", ":")),
            diff_text=xml_diff(current, proposed),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=VmChangePlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return VmChangePreview(plan, token)

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
        change_type: str | None = None,
    ) -> VmChangePlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(VmChangePlan, plan_id)
            if plan is None or plan.status != VmChangePlanStatus.PREVIEW:
                raise VmChangeError("VM change plan is unavailable")
            if plan.host_id != host_id or plan.vm_uuid != vm_uuid:
                raise VmChangeConflict("VM change plan scope does not match")
            if change_type is not None and plan.change_type != change_type:
                raise VmChangeConflict("VM change plan type does not match")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = VmChangePlanStatus.EXPIRED
                raise VmChangeError("VM change plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise VmChangeError("VM change confirmation is invalid")
            plan.status = VmChangePlanStatus.CONFIRMED
            plan.confirmed_at = now
            return plan

    def execute(
        self,
        plan_id: str,
        *,
        task_id: str,
        expected_change_type: str | None = None,
        progress: ChangeProgress | None = None,
    ) -> str:
        try:
            plan = self.plan_store.load(plan_id, VmChangePlanStatus.CONFIRMED)
        except ValueError as exc:
            raise VmChangeError("VM change plan is not confirmed") from exc
        if expected_change_type is not None and plan.change_type != expected_change_type:
            raise VmChangeConflict("VM change task type does not match plan")
        self.locks.acquire(
            plan.host_id,
            ResourceType.VIRTUAL_MACHINE,
            plan.vm_uuid,
            task_id,
        )
        applied = False
        try:
            self.plan_store.mark_running(plan.id)
            _notify(progress, 1, "Refresh authoritative VM XML")
            before = self.discovery.read_one(plan.host_id, plan.vm_uuid)
            self.store.refresh_one(plan.host_id, ResourceType.VIRTUAL_MACHINE, before)
            self.guard.verify(_base_version(plan))
            if before.persistent_hash != plan.base_persistent_hash:
                raise VmChangeConflict("VM XML changed after preview")
            _notify(progress, 2, "Apply validated persistent VM XML")
            result = self._define(plan.host_id, plan.proposed_xml)
            _require_success(result, "libvirt rejected proposed VM XML")
            applied = True
            _notify(progress, 3, "Verify persistent VM XML")
            final = self.discovery.read_one(plan.host_id, plan.vm_uuid)
            expected_after_hash = self._verified_after_hash(plan, final)
            self.store.accept_expected_change(
                plan.resource_index_id,
                expected_before_hash=plan.base_persistent_hash,
                expected_after_hash=expected_after_hash,
                observation=final,
            )
            self.plan_store.mark_succeeded(plan.id)
            return f"{plan.change_type} updated; vm={plan.vm_uuid}; reboot_required=true"
        except Exception as exc:
            rollback_error = self._rollback(plan) if applied else None
            self.plan_store.mark_failed(plan.id, _error_message(exc, rollback_error))
            raise
        finally:
            self.locks.release(
                plan.host_id,
                ResourceType.VIRTUAL_MACHINE,
                plan.vm_uuid,
                task_id,
            )

    def _verified_after_hash(
        self,
        plan: VmChangePlan,
        observation: ResourceObservation,
    ) -> str:
        if observation.persistent_hash != plan.proposed_persistent_hash:
            raise ValueError("authoritative VM XML does not match proposed XML")
        return plan.proposed_persistent_hash

    def _validate_remote(self, host_id: str, proposed_xml: bytes) -> None:
        host = self._host(host_id)
        result = self.executor.run(
            host_id,
            CommandSpec("virt-xml-validate", ("-", "domain")),
            sudo=_uses_sudo(host),
            timeout=30,
            stdin=proposed_xml,
            env={"LC_ALL": "C"},
            sensitive=True,
        )
        _require_success(result, "proposed VM XML failed schema validation")

    def _define(self, host_id: str, content: bytes) -> CommandResult:
        host = self._host(host_id)
        return self.executor.run(
            host_id,
            CommandSpec(
                "virsh",
                ("-c", host.libvirt_uri, "define", "/dev/stdin", "--validate"),
            ),
            sudo=_uses_sudo(host),
            timeout=60,
            stdin=content,
            env={"LC_ALL": "C"},
            sensitive=True,
        )

    def _rollback(self, plan: VmChangePlan) -> str | None:
        try:
            _require_success(
                self._define(plan.host_id, plan.original_xml),
                "VM XML rollback command failed",
            )
            restored = self.discovery.read_one(plan.host_id, plan.vm_uuid)
            if restored.persistent_hash != plan.base_persistent_hash:
                raise VmChangeError("VM XML rollback verification failed")
            return None
        except Exception as exc:
            return str(exc)

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise VmChangeError("host not found")
            return host


def _base_version(plan: VmChangePlan) -> ResourceBaseVersion:
    return ResourceBaseVersion(
        plan.resource_index_id,
        plan.host_id,
        ResourceType.VIRTUAL_MACHINE,
        plan.vm_uuid,
        plan.base_generation,
        plan.base_persistent_hash,
        None,
    )


def _uses_sudo(host: Host) -> bool:
    return host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS


def _require_success(result: CommandResult, message: str) -> None:
    if result.exit_code != 0 or result.timed_out or result.cancelled:
        raise VmChangeError(message)
    if result.stdout_truncated or result.stderr_truncated:
        raise VmChangeError("VM XML command output exceeded safety limit")


def _error_message(error: Exception, rollback_error: str | None) -> str:
    if rollback_error is None:
        return str(error)
    return f"{error}; rollback failed: {rollback_error}"


def _notify(progress: ChangeProgress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)
