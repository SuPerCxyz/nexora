"""Preview, confirm, execute, and verify VM deletion or rename."""

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
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.contracts import ResourceObservation
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.remove_contracts import VmRemoveInput
from nexora.vms.remove_models import VmRemovePlan
from nexora.vms.remove_store import VmRemovePlanStore

PLAN_TTL = timedelta(minutes=10)
RemoveProgress = Callable[[int, str], None]


class VmRemoveError(RuntimeError):
    pass


class VmRemoveConflict(VmRemoveError):
    pass


@dataclass(frozen=True)
class VmRemovePreview:
    plan: VmRemovePlan
    confirmation_token: str


class VmRemoveService:
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
        self.plans = VmRemovePlanStore(database)

    def preview(self, remove: VmRemoveInput) -> VmRemovePreview:
        remove.validate()
        observation = self.discovery.read_one(remove.host_id, remove.vm_uuid)
        resource = self.store.refresh_one(
            remove.host_id,
            ResourceType.VIRTUAL_MACHINE,
            observation,
        )
        self.guard.verify(
            ResourceBaseVersion(
                resource.id,
                remove.host_id,
                ResourceType.VIRTUAL_MACHINE,
                remove.vm_uuid,
                remove.generation,
                remove.persistent_hash,
                None,
            )
        )
        if bool(observation.details.get("active")):
            raise VmRemoveConflict("VM must be shut down before delete or rename")
        if not bool(observation.details.get("persistent")):
            raise VmRemoveConflict("transient VMs cannot be deleted or renamed")
        if (
            remove.operation == "rename"
            and remove.target_name != remove.vm_name
            and remove.target_name is not None
            and self._name_taken(remove.host_id, remove.target_name)
        ):
            raise VmRemoveConflict("VM rename target name already exists")
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = VmRemovePlan(
            id=str(uuid4()),
            host_id=remove.host_id,
            vm_uuid=remove.vm_uuid,
            vm_name=remove.vm_name,
            operation=remove.operation,
            input_json=remove.encode(),
            diff_text=_diff_text(remove, observation),
            confirmation_digest=sha256(token.encode()).hexdigest(),
            status=VmChangePlanStatus.PREVIEW,
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return VmRemovePreview(plan, token)

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
        confirmation_name: str,
    ) -> VmRemovePlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(VmRemovePlan, plan_id)
            if plan is None or plan.status != VmChangePlanStatus.PREVIEW:
                raise VmRemoveError("VM remove plan is unavailable")
            if plan.host_id != host_id or plan.vm_uuid != vm_uuid:
                raise VmRemoveConflict("VM remove plan scope does not match")
            resource = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.native_id == vm_uuid,
                )
            )
            if resource is None or not hmac.compare_digest(
                confirmation_name, resource.display_name
            ):
                raise VmRemoveError("VM name confirmation is invalid")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = VmChangePlanStatus.EXPIRED
                raise VmRemoveError("VM remove plan expired")
            submitted = sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise VmRemoveError("VM remove confirmation is invalid")
            plan.status = VmChangePlanStatus.CONFIRMED
            plan.confirmed_at = now
            return plan

    def execute(
        self,
        plan_id: str,
        *,
        task_id: str,
        progress: RemoveProgress | None = None,
    ) -> str:
        try:
            plan = self.plans.load_for_execution(plan_id)
        except ValueError as exc:
            raise VmRemoveError("VM remove plan is not confirmed") from exc
        remove = VmRemoveInput.decode(plan.input_json)
        self.locks.acquire(
            plan.host_id,
            ResourceType.VIRTUAL_MACHINE,
            plan.vm_uuid,
            task_id,
        )
        try:
            self.plans.mark_running(plan.id)
            _notify(progress, 1, "Refresh authoritative VM state")
            observation = self.discovery.read_one(plan.host_id, plan.vm_uuid)
            resource = self.store.refresh_one(
                plan.host_id,
                ResourceType.VIRTUAL_MACHINE,
                observation,
            )
            self.guard.verify(
                ResourceBaseVersion(
                    resource.id,
                    plan.host_id,
                    ResourceType.VIRTUAL_MACHINE,
                    plan.vm_uuid,
                    remove.generation,
                    remove.persistent_hash,
                    None,
                )
            )
            if bool(observation.details.get("active")):
                raise VmRemoveConflict("VM became active before execution")
            if remove.operation == "rename":
                return self._execute_rename(plan, remove, progress)
            return self._execute_delete(plan, remove, observation, progress)
        except Exception as exc:
            self.plans.mark_failed(plan.id, str(exc))
            raise
        finally:
            self.locks.release(
                plan.host_id,
                ResourceType.VIRTUAL_MACHINE,
                plan.vm_uuid,
                task_id,
            )

    def _execute_rename(
        self,
        plan: VmRemovePlan,
        remove: VmRemoveInput,
        progress: RemoveProgress | None,
    ) -> str:
        _notify(progress, 2, f"Rename VM to {remove.target_name}")
        if remove.target_name is None:
            raise VmRemoveError("VM rename target name is unavailable")
        _require_success(
            self._virsh(plan.host_id, ("domrename", plan.vm_uuid, remove.target_name)),
            "VM rename failed",
        )
        _notify(progress, 3, "Verify authoritative VM name")
        final = self.discovery.read_one(plan.host_id, plan.vm_uuid)
        if not _renamed(final, remove.target_name):
            raise VmRemoveError("renamed VM verification failed")
        self.store.refresh_one(plan.host_id, ResourceType.VIRTUAL_MACHINE, final)
        self.plans.mark_succeeded(plan.id)
        return f"VM renamed; vm={plan.vm_uuid}; name={remove.target_name}"

    def _execute_delete(
        self,
        plan: VmRemovePlan,
        remove: VmRemoveInput,
        observation: ResourceObservation,
        progress: RemoveProgress | None,
    ) -> str:
        _notify(progress, 2, "Undefine VM")
        arguments: tuple[str, ...] = ("undefine", plan.vm_uuid)
        if remove.remove_disks:
            arguments = (*arguments, "--remove-all-storage")
        if remove.remove_nvram:
            arguments = (*arguments, "--nvram")
        _require_success(self._virsh(plan.host_id, arguments), "VM undefine failed")
        _notify(progress, 3, "Verify VM is absent from authoritative inventory")
        self.discovery.run(plan.host_id)
        if self._still_present(plan.host_id, plan.vm_uuid):
            raise VmRemoveError("VM is still present after undefine")
        self.plans.mark_succeeded(plan.id)
        removed = (
            " with disk and NVRAM"
            if remove.remove_disks and remove.remove_nvram
            else (
                " with disks"
                if remove.remove_disks
                else (" with NVRAM" if remove.remove_nvram else "")
            )
        )
        return f"VM deleted; vm={plan.vm_uuid}{removed}"

    def _virsh(self, host_id: str, arguments: tuple[str, ...]) -> CommandResult:
        host = self._host(host_id)
        return self.executor.run(
            host_id,
            CommandSpec("virsh", ("-c", host.libvirt_uri, *arguments)),
            sudo=host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS,
            timeout=60,
            env={"LC_ALL": "C"},
        )

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise VmRemoveError("host not found")
            return host

    def _name_taken(self, host_id: str, name: str) -> bool:
        with self.database.session() as session:
            match = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.display_name == name,
                    ResourceIndex.status != ResourceStatus.MISSING,
                )
            )
            return match is not None

    def _still_present(self, host_id: str, vm_uuid: str) -> bool:
        with self.database.session() as session:
            return (
                session.scalar(
                    select(ResourceIndex).where(
                        ResourceIndex.host_id == host_id,
                        ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                        ResourceIndex.native_id == vm_uuid,
                        ResourceIndex.status != ResourceStatus.MISSING,
                    )
                )
                is not None
            )


def _diff_text(remove: VmRemoveInput, observation: ResourceObservation) -> str:
    details = observation.details
    disks_value = details.get("disks")
    disks = [
        str(item.get("source"))
        for item in (disks_value if isinstance(disks_value, list) else [])
        if isinstance(item, dict) and item.get("device") == "disk"
    ]
    nvram = details.get("nvram_path")
    if remove.operation == "rename":
        return "\n".join(
            [
                f"- {remove.vm_name}",
                f"+ {remove.target_name}",
                "",
                "仅重命名虚拟机定义，不移动磁盘或修改硬件配置。",
            ]
        )
    lines = [f"undefine 虚拟机 {remove.vm_name} ({remove.vm_uuid})"]
    if remove.remove_disks and disks:
        lines.append("删除磁盘:")
        lines.extend(f"  - {path}" for path in disks)
    if remove.remove_nvram and nvram:
        lines.append(f"删除 NVRAM: {nvram}")
    if not remove.remove_disks and not remove.remove_nvram:
        lines.append("保留磁盘与 NVRAM(仅移除定义).")
    return "\n".join(lines)


def _renamed(observation: ResourceObservation, target_name: str) -> bool:
    name = observation.details.get("name")
    return name == target_name


def _notify(progress: RemoveProgress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)


def _require_success(result: CommandResult, message: str) -> None:
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    ):
        raise VmRemoveError(message)
