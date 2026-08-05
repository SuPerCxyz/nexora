"""Locked execution and verification of confirmed volume mutation plans."""

import json
from collections.abc import Callable

from nexora.resources.models import ResourceStatus, ResourceType
from nexora.resources.storage_parser import volume_configuration_hash
from nexora.storage.plan_utils import notify
from nexora.storage.volume_authority import StorageVolumeAuthority, VerifiedVolume
from nexora.storage.volume_contracts import StorageVolumeMutationInput
from nexora.storage.volume_models import StorageVolumeChangePlan
from nexora.storage.volume_plan_store import StorageVolumePlanStore
from nexora.storage.volume_remote import StorageVolumeRemoteCommands
from nexora.storage.volume_service import StorageVolumeConflict, StorageVolumeError
from nexora.tasks.locks import ResourceLockStore

ChangeProgress = Callable[[int, str], None]


class StorageVolumeMutationExecutor:
    def __init__(
        self,
        authority: StorageVolumeAuthority,
        locks: ResourceLockStore,
        commands: StorageVolumeRemoteCommands,
        plans: StorageVolumePlanStore,
    ) -> None:
        self.authority = authority
        self.locks = locks
        self.commands = commands
        self.plans = plans

    def execute(
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
        was_recovery = plan.status == "running"
        change = StorageVolumeMutationInput.decode(plan.input_json, plan.operation)
        acquired: list[tuple[ResourceType, str]] = []
        try:
            for resource_type, native_id in (
                (ResourceType.STORAGE_POOL, plan.pool_uuid),
                (ResourceType.STORAGE_VOLUME, change.volume_native_id),
            ):
                self.locks.acquire(
                    plan.host_id,
                    resource_type,
                    native_id,
                    task_id,
                )
                acquired.append((resource_type, native_id))
            self.plans.mark_running(plan.id)
            return self._execute_locked(plan, change, was_recovery, progress)
        except Exception as exc:
            self.plans.mark_failed(plan.id, str(exc))
            raise
        finally:
            for resource_type, native_id in reversed(acquired):
                self.locks.release(
                    plan.host_id,
                    resource_type,
                    native_id,
                    task_id,
                )

    def _execute_locked(
        self,
        plan: StorageVolumeChangePlan,
        change: StorageVolumeMutationInput,
        was_recovery: bool,
        progress: ChangeProgress | None,
    ) -> str:
        notify(progress, 1, "Refresh authoritative pool, volume, and VM inventory")
        if was_recovery:
            recovered = self._verify_recovery(plan, change)
            if recovered is not None:
                return recovered
        verified = self.authority.refresh_and_verify(change, operation=plan.operation)
        if plan.operation == "resize":
            return self._resize(plan, change, verified, progress)
        return self._delete(plan, change, verified, progress)

    def _verify_recovery(
        self,
        plan: StorageVolumeChangePlan,
        change: StorageVolumeMutationInput,
    ) -> str | None:
        self.authority.storage_discovery.run(plan.host_id)
        if plan.operation == "delete" and self.authority.is_missing(change):
            self.plans.mark_succeeded(
                plan.id,
                change.volume_resource_id,
                change.volume_native_id,
            )
            return f"storage volume deletion already verified; name={change.volume_name}"
        current = self.authority.resource(change.volume_resource_id)
        details = json.loads(current.details_json)
        if plan.operation == "resize" and _int_value(details.get("capacity_bytes")) == _target(
            change
        ):
            self.plans.mark_succeeded(plan.id, current.id, current.native_id)
            return f"storage volume resize already verified; name={change.volume_name}"
        return None

    def _resize(
        self,
        plan: StorageVolumeChangePlan,
        change: StorageVolumeMutationInput,
        verified: VerifiedVolume,
        progress: ChangeProgress | None,
    ) -> str:
        target = _target(change)
        current = _int_value(verified.details.get("capacity_bytes"))
        if current != change.current_capacity_bytes:
            raise StorageVolumeConflict("storage volume capacity changed after preview")
        notify(progress, 2, "Increase storage volume capacity without shrinking")
        result = self.commands.virsh(
            plan.host_id,
            ("vol-resize", change.volume_key, str(target), "--pool", plan.pool_uuid),
        )
        _require_success(result)
        notify(progress, 3, "Verify authoritative storage volume capacity")
        observation = self.authority.storage_discovery.read_volume(
            plan.host_id,
            plan.pool_uuid,
            change.volume_key,
        )
        proposed = plan.proposed_xml
        if proposed is None:
            raise StorageVolumeError("storage volume resize XML is missing")
        final = self.authority.storage_discovery.store.accept_expected_change(
            change.volume_resource_id,
            expected_before_hash=change.volume_hash,
            expected_after_hash=volume_configuration_hash(proposed),
            observation=observation,
        )
        details = json.loads(final.details_json)
        if int(details.get("capacity_bytes", 0)) != target:
            raise StorageVolumeError("resized storage volume verification failed")
        self.plans.mark_succeeded(plan.id, final.id, final.native_id)
        return f"storage volume resized; name={change.volume_name}; capacity={target}"

    def _delete(
        self,
        plan: StorageVolumeChangePlan,
        change: StorageVolumeMutationInput,
        verified: VerifiedVolume,
        progress: ChangeProgress | None,
    ) -> str:
        notify(progress, 2, "Delete explicitly selected unreferenced storage volume")
        result = self.commands.virsh(
            plan.host_id,
            ("vol-delete", change.volume_key, "--pool", plan.pool_uuid),
        )
        _require_success(result)
        notify(progress, 3, "Verify authoritative storage volume absence")
        self.authority.storage_discovery.run(plan.host_id)
        final = self.authority.resource(change.volume_resource_id)
        if final.status != ResourceStatus.MISSING:
            raise StorageVolumeError("deleted storage volume verification failed")
        self.plans.mark_succeeded(plan.id, final.id, final.native_id)
        return f"storage volume deleted; name={verified.volume.display_name}"


def _target(change: StorageVolumeMutationInput) -> int:
    target = change.target_capacity_bytes
    if target is None:
        raise StorageVolumeError("storage volume resize target is missing")
    return target


def _int_value(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise StorageVolumeConflict("storage volume capacity is invalid")
    return value


def _require_success(result: object) -> None:
    exit_code = getattr(result, "exit_code", None)
    if exit_code != 0:
        stderr = getattr(result, "stderr", b"")
        message = stderr.decode(errors="replace").strip() if isinstance(stderr, bytes) else ""
        raise StorageVolumeError(message or "remote storage volume command failed")
