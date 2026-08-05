"""State-aware, UUID-scoped storage pool lifecycle operations."""

from collections.abc import Callable

from nexora.resources.conflicts import ResourceWriteGuard
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.storage.remote_ops import StoragePoolRemoteCommands, require_success
from nexora.storage.task_contracts import StoragePoolAction, StoragePoolLifecycleInput
from nexora.tasks.locks import ResourceLockStore

LifecycleProgress = Callable[[int, str], None]


class StoragePoolLifecycleError(RuntimeError):
    pass


class StoragePoolLifecycleService:
    def __init__(
        self,
        discovery: StorageDiscoveryService,
        store: ResourceIndexStore,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
        commands: StoragePoolRemoteCommands,
    ) -> None:
        self.discovery = discovery
        self.store = store
        self.guard = guard
        self.locks = locks
        self.commands = commands

    def execute(
        self,
        task_input: StoragePoolLifecycleInput,
        *,
        task_id: str,
        progress: LifecycleProgress | None = None,
    ) -> str:
        base = task_input.base
        self.locks.acquire(
            base.host_id,
            ResourceType.STORAGE_POOL,
            base.native_id,
            task_id,
        )
        try:
            _notify(progress, 1, "Refresh authoritative storage pool state")
            before = self.discovery.read_pool(base.host_id, base.native_id)
            self.store.refresh_one(base.host_id, ResourceType.STORAGE_POOL, before)
            self.guard.verify(base)
            self._validate(task_input.action, before.details)
            if task_input.action == StoragePoolAction.REFRESH or not _already_matches(
                task_input.action, before.details
            ):
                _notify(progress, 2, f"Execute storage pool {task_input.action}")
                require_success(
                    self.commands.virsh(
                        base.host_id,
                        _command(task_input.action, base.native_id),
                    ),
                    "libvirt storage lifecycle command failed",
                )
            else:
                _notify(progress, 2, "Requested storage pool state already exists")
            _notify(progress, 3, "Verify authoritative storage pool state")
            final = self.discovery.read_pool(base.host_id, base.native_id)
            if not _already_matches(task_input.action, final.details):
                raise StoragePoolLifecycleError("storage pool final state verification failed")
            if final.persistent_hash != before.persistent_hash:
                raise StoragePoolLifecycleError("storage pool XML changed during lifecycle action")
            self.store.refresh_one(base.host_id, ResourceType.STORAGE_POOL, final)
            return f"action={task_input.action}; pool={base.native_id}"
        finally:
            self.locks.release(
                base.host_id,
                ResourceType.STORAGE_POOL,
                base.native_id,
                task_id,
            )

    @staticmethod
    def _validate(action: StoragePoolAction, details: dict[str, object]) -> None:
        if details.get("pool_type") not in {"dir", "netfs"}:
            raise StoragePoolLifecycleError("storage pool type is read-only")
        if not bool(details.get("persistent")):
            raise StoragePoolLifecycleError("transient storage pool cannot be changed")
        if action == StoragePoolAction.REFRESH and not bool(details.get("active")):
            raise StoragePoolLifecycleError("inactive storage pool cannot be refreshed")


def _command(action: StoragePoolAction, pool_uuid: str) -> tuple[str, ...]:
    commands = {
        StoragePoolAction.START: ("pool-start", pool_uuid),
        StoragePoolAction.STOP: ("pool-destroy", pool_uuid),
        StoragePoolAction.REFRESH: ("pool-refresh", pool_uuid),
        StoragePoolAction.AUTOSTART_ENABLE: ("pool-autostart", pool_uuid),
        StoragePoolAction.AUTOSTART_DISABLE: ("pool-autostart", pool_uuid, "--disable"),
    }
    return commands[action]


def _already_matches(action: StoragePoolAction, details: dict[str, object]) -> bool:
    if action == StoragePoolAction.START:
        return bool(details.get("active"))
    if action == StoragePoolAction.STOP:
        return not bool(details.get("active"))
    if action == StoragePoolAction.AUTOSTART_ENABLE:
        return bool(details.get("autostart"))
    if action == StoragePoolAction.AUTOSTART_DISABLE:
        return not bool(details.get("autostart"))
    return action == StoragePoolAction.REFRESH and bool(details.get("active"))


def _notify(progress: LifecycleProgress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)
