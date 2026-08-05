"""State-aware, UUID-scoped libvirt domain lifecycle operations."""

import time
from collections.abc import Callable

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.conflicts import ResourceWriteGuard
from nexora.resources.contracts import ResourceObservation
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceType
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.contracts import LifecycleAction, LifecycleTaskInput

LifecycleProgress = Callable[[int, str], None]
CancellationCheck = Callable[[], bool]


class LifecycleOperationError(RuntimeError):
    pass


class LifecycleStateConflict(LifecycleOperationError):
    pass


class LifecycleCancelled(LifecycleOperationError):
    pass


class DomainLifecycleService:
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        discovery: DomainDiscoveryService,
        store: ResourceIndexStore,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.database = database
        self.executor = executor
        self.discovery = discovery
        self.store = store
        self.guard = guard
        self.locks = locks
        self.sleeper = sleeper
        self.clock = clock

    def execute(
        self,
        task_input: LifecycleTaskInput,
        *,
        task_id: str,
        progress: LifecycleProgress | None = None,
        cancellation_requested: CancellationCheck | None = None,
    ) -> str:
        base = task_input.base
        self.locks.acquire(
            base.host_id,
            ResourceType.VIRTUAL_MACHINE,
            base.native_id,
            task_id,
        )
        try:
            _notify(progress, 1, "Refresh authoritative VM state")
            before = self.discovery.read_one(base.host_id, base.native_id)
            indexed = self.store.refresh_one(
                base.host_id,
                ResourceType.VIRTUAL_MACHINE,
                before,
            )
            self.guard.verify(base)
            self._validate_action(task_input.action, before.details)
            _cancel(cancellation_requested)
            _notify(progress, 2, f"Execute {task_input.action}")
            host = self._host(base.host_id)
            result = self.executor.run(
                base.host_id,
                CommandSpec(
                    "virsh",
                    ("-c", host.libvirt_uri, *_command(task_input.action, base.native_id)),
                ),
                sudo=_uses_sudo(host),
                timeout=60,
                env={"LC_ALL": "C"},
            )
            _require_success(result)
            _notify(progress, 3, "Verify final VM state")
            final = self._wait_for_expected(
                task_input,
                cancellation_requested=cancellation_requested,
            )
            self.store.refresh_one(
                base.host_id,
                ResourceType.VIRTUAL_MACHINE,
                final,
            )
            return (
                f"action={task_input.action}; vm={indexed.native_id}; "
                f"state={final.details.get('state', 'unknown')}"
            )
        finally:
            self.locks.release(
                base.host_id,
                ResourceType.VIRTUAL_MACHINE,
                base.native_id,
                task_id,
            )

    def _wait_for_expected(
        self,
        task_input: LifecycleTaskInput,
        *,
        cancellation_requested: CancellationCheck | None,
    ) -> ResourceObservation:
        deadline = self.clock() + 60
        latest = self.discovery.read_one(
            task_input.base.host_id,
            task_input.base.native_id,
        )
        while not _matches(task_input.action, latest.details):
            _cancel(cancellation_requested)
            if self.clock() >= deadline:
                raise LifecycleOperationError("VM did not reach the expected final state")
            self.sleeper(0.5)
            latest = self.discovery.read_one(
                task_input.base.host_id,
                task_input.base.native_id,
            )
        return latest

    def _validate_action(self, action: LifecycleAction, details: dict[str, object]) -> None:
        state = _state(details)
        active = bool(details.get("active"))
        persistent = bool(details.get("persistent"))
        allowed = {
            LifecycleAction.START: not active and persistent,
            LifecycleAction.SHUTDOWN: state == "running",
            LifecycleAction.FORCE_OFF: active,
            LifecycleAction.REBOOT: state == "running",
            LifecycleAction.FORCE_REBOOT: active,
            LifecycleAction.PAUSE: state == "running",
            LifecycleAction.RESUME: state == "paused",
            LifecycleAction.MANAGED_SAVE: active and persistent,
            LifecycleAction.AUTOSTART_ENABLE: persistent,
            LifecycleAction.AUTOSTART_DISABLE: persistent,
        }
        if not allowed[action]:
            raise LifecycleStateConflict(f"{action} is not valid while VM state is {state}")

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise LifecycleOperationError("host not found")
            return host


def _command(action: LifecycleAction, domain_uuid: str) -> tuple[str, ...]:
    commands = {
        LifecycleAction.START: ("start", domain_uuid),
        LifecycleAction.SHUTDOWN: ("shutdown", domain_uuid),
        LifecycleAction.FORCE_OFF: ("destroy", domain_uuid),
        LifecycleAction.REBOOT: ("reboot", domain_uuid),
        LifecycleAction.FORCE_REBOOT: ("reset", domain_uuid),
        LifecycleAction.PAUSE: ("suspend", domain_uuid),
        LifecycleAction.RESUME: ("resume", domain_uuid),
        LifecycleAction.MANAGED_SAVE: ("managedsave", domain_uuid),
        LifecycleAction.AUTOSTART_ENABLE: ("autostart", domain_uuid),
        LifecycleAction.AUTOSTART_DISABLE: ("autostart", domain_uuid, "--disable"),
    }
    return commands[action]


def _matches(action: LifecycleAction, details: dict[str, object]) -> bool:
    state = _state(details)
    if action in {LifecycleAction.SHUTDOWN, LifecycleAction.FORCE_OFF}:
        return state == "shut off"
    if action == LifecycleAction.MANAGED_SAVE:
        return state == "shut off" and bool(details.get("managed_save"))
    if action == LifecycleAction.PAUSE:
        return state == "paused"
    if action in {LifecycleAction.AUTOSTART_ENABLE, LifecycleAction.AUTOSTART_DISABLE}:
        return bool(details.get("autostart")) == (action == LifecycleAction.AUTOSTART_ENABLE)
    return state == "running"


def _state(details: dict[str, object]) -> str:
    value = details.get("state")
    if not isinstance(value, str):
        raise LifecycleOperationError("VM state is unavailable")
    return value.lower()


def _uses_sudo(host: Host) -> bool:
    return host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS


def _require_success(result: CommandResult) -> None:
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    ):
        raise LifecycleOperationError("libvirt lifecycle command failed")


def _cancel(check: CancellationCheck | None) -> None:
    if check is not None and check():
        raise LifecycleCancelled("VM lifecycle task was cancelled")


def _notify(progress: LifecycleProgress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)
