import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import func, select

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.remote.executor import RemoteCommandAudit, RemoteExecutor
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile
from nexora.resources.conflicts import (
    ResourceBaseVersion,
    ResourceWriteConflict,
    ResourceWriteGuard,
)
from nexora.resources.contracts import ResourceObservation
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.locks import ResourceLock, ResourceLockConflict, ResourceLockStore
from nexora.vms.contracts import LifecycleAction, LifecycleTaskInput
from nexora.vms.lifecycle import DomainLifecycleService, LifecycleStateConflict

DOMAIN_UUID = "11111111-1111-1111-1111-111111111111"


class Resolver:
    def __init__(self, known_hosts: Path) -> None:
        self.known_hosts = known_hosts

    def resolve(self, _host_id: str) -> SSHConnectionProfile:
        return SSHConnectionProfile(SSHConnection("node", 22, "root", self.known_hosts))


class Audit:
    def record(self, _event: RemoteCommandAudit) -> None:
        return


class LifecycleBackend:
    def __init__(self, state: dict[str, object]) -> None:
        self.state = state
        self.commands: list[str] = []

    def run(
        self,
        _profile: SSHConnectionProfile,
        command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult:
        del timeout, stdin, cancel_event
        self.commands.append(command)
        if f" start {DOMAIN_UUID}" in command:
            self.state.update(state="running", active=True)
        elif f" shutdown {DOMAIN_UUID}" in command or f" destroy {DOMAIN_UUID}" in command:
            self.state.update(state="shut off", active=False)
        elif f" suspend {DOMAIN_UUID}" in command:
            self.state.update(state="paused", active=True)
        elif f" resume {DOMAIN_UUID}" in command:
            self.state.update(state="running", active=True)
        elif f" managedsave {DOMAIN_UUID}" in command:
            self.state.update(state="shut off", active=False, managed_save=True)
        elif f" autostart {DOMAIN_UUID} --disable" in command:
            self.state["autostart"] = False
        elif f" autostart {DOMAIN_UUID}" in command:
            self.state["autostart"] = True
        elif f" reboot {DOMAIN_UUID}" in command or f" reset {DOMAIN_UUID}" in command:
            self.state.update(state="running", active=True)
        return ProcessResult(0, b"", b"", False, False, False, False, 0.01)


class Discovery:
    def __init__(self, state: dict[str, object]) -> None:
        self.state = state

    def read_one(self, _host_id: str, _domain_uuid: str) -> ResourceObservation:
        return _observation(
            state=str(self.state["state"]),
            active=bool(self.state["active"]),
            xml_hash=str(self.state["hash"]),
            autostart=bool(self.state.get("autostart", False)),
            managed_save=bool(self.state.get("managed_save", False)),
        )


def test_start_uses_uuid_lock_and_refreshes_final_authoritative_state(
    settings: Settings,
) -> None:
    database, service, state, backend, base = _runtime(settings)

    result = service.execute(
        LifecycleTaskInput(LifecycleAction.START, base),
        task_id="task-start",
    )

    assert "state=running" in result
    assert any(f"virsh -c qemu:///system start {DOMAIN_UUID}" in item for item in backend.commands)
    with database.session() as session:
        resource = session.get(ResourceIndex, base.resource_id)
        lock_count = session.scalar(select(func.count()).select_from(ResourceLock))
        assert resource is not None
        assert "running" == json.loads(resource.details_json)["state"]
        assert 0 == lock_count
    assert "running" == state["state"]
    database.dispose()


def test_out_of_band_xml_change_blocks_command_before_execution(settings: Settings) -> None:
    database, service, state, backend, base = _runtime(settings)
    state["hash"] = "hash-b"

    with pytest.raises(ResourceWriteConflict):
        service.execute(
            LifecycleTaskInput(LifecycleAction.START, base),
            task_id="task-conflict",
        )

    assert not backend.commands
    database.dispose()


def test_invalid_lifecycle_state_is_rejected(settings: Settings) -> None:
    database, service, _state, backend, base = _runtime(settings)

    with pytest.raises(LifecycleStateConflict):
        service.execute(
            LifecycleTaskInput(LifecycleAction.SHUTDOWN, base),
            task_id="task-invalid",
        )

    assert not backend.commands
    database.dispose()


def test_resource_lock_rejects_concurrent_vm_writer(settings: Settings) -> None:
    database, _service, _state, _backend, _base = _runtime(settings)
    locks = ResourceLockStore(database)
    locks.acquire("host-1", ResourceType.VIRTUAL_MACHINE, DOMAIN_UUID, "task-one")

    with pytest.raises(ResourceLockConflict):
        locks.acquire("host-1", ResourceType.VIRTUAL_MACHINE, DOMAIN_UUID, "task-two")

    locks.release("host-1", ResourceType.VIRTUAL_MACHINE, DOMAIN_UUID, "task-one")
    database.dispose()


def test_resource_lock_heartbeat_renews_task_leases(settings: Settings) -> None:
    database, _service, _state, _backend, _base = _runtime(settings)
    locks = ResourceLockStore(database)
    locks.acquire("host-1", ResourceType.VIRTUAL_MACHINE, DOMAIN_UUID, "task-one")
    with database.session() as session:
        original_expiry = session.scalar(select(ResourceLock.expires_at))

    assert 1 == locks.renew_task("task-one", lease_seconds=600)

    with database.session() as session:
        renewed_expiry = session.scalar(select(ResourceLock.expires_at))
    assert original_expiry is not None
    assert renewed_expiry is not None
    assert original_expiry < renewed_expiry
    locks.release("host-1", ResourceType.VIRTUAL_MACHINE, DOMAIN_UUID, "task-one")
    database.dispose()


@pytest.mark.parametrize(
    ("action", "initial_state", "active", "autostart", "expected_state"),
    [
        (LifecycleAction.SHUTDOWN, "running", True, False, "shut off"),
        (LifecycleAction.FORCE_OFF, "running", True, False, "shut off"),
        (LifecycleAction.REBOOT, "running", True, False, "running"),
        (LifecycleAction.FORCE_REBOOT, "running", True, False, "running"),
        (LifecycleAction.PAUSE, "running", True, False, "paused"),
        (LifecycleAction.RESUME, "paused", True, False, "running"),
        (LifecycleAction.MANAGED_SAVE, "running", True, False, "shut off"),
        (LifecycleAction.AUTOSTART_ENABLE, "shut off", False, False, "shut off"),
        (LifecycleAction.AUTOSTART_DISABLE, "shut off", False, True, "shut off"),
    ],
)
def test_supported_lifecycle_action_reaches_verified_state(
    settings: Settings,
    action: LifecycleAction,
    initial_state: str,
    active: bool,
    autostart: bool,
    expected_state: str,
) -> None:
    database, service, state, _backend, base = _runtime(
        settings,
        initial_state=initial_state,
        active=active,
        autostart=autostart,
    )

    service.execute(LifecycleTaskInput(action, base), task_id=f"task-{action}")

    assert expected_state == state["state"]
    database.dispose()


def _runtime(
    settings: Settings,
    *,
    initial_state: str = "shut off",
    active: bool = False,
    autostart: bool = False,
) -> tuple[
    Database,
    DomainLifecycleService,
    dict[str, object],
    LifecycleBackend,
    ResourceBaseVersion,
]:
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    state: dict[str, object] = {
        "state": initial_state,
        "active": active,
        "hash": "hash-a",
        "autostart": autostart,
        "managed_save": False,
    }
    store = ResourceIndexStore(database)
    result = store.apply_snapshot(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        [
            _observation(
                state=initial_state,
                active=active,
                xml_hash="hash-a",
                autostart=autostart,
            )
        ],
    )
    resource = result.resources[0]
    base = ResourceBaseVersion(
        resource.id,
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        DOMAIN_UUID,
        result.generation,
        resource.persistent_hash,
        resource.live_hash,
    )
    backend = LifecycleBackend(state)
    executor = RemoteExecutor(
        Resolver(settings.data_dir / "hostkeys" / "known_hosts"),
        Audit(),
        backend=backend,
    )
    service = DomainLifecycleService(
        database,
        executor,
        Discovery(state),
        store,
        ResourceWriteGuard(database),
        ResourceLockStore(database),
        sleeper=lambda _seconds: None,
    )
    return database, service, state, backend, base


def _observation(
    *,
    state: str,
    active: bool,
    xml_hash: str,
    autostart: bool = False,
    managed_save: bool = False,
) -> ResourceObservation:
    return ResourceObservation(
        native_id=DOMAIN_UUID,
        display_name="vm-one",
        status=ResourceStatus.MANAGED,
        persistent_hash=xml_hash,
        live_hash=None,
        details={
            "state": state,
            "active": active,
            "persistent": True,
            "autostart": autostart,
            "managed_save": managed_save,
        },
    )


def _add_host(database: Database) -> None:
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(
            Host(
                id="host-1",
                name="node",
                address="node.example.test",
                ssh_port=22,
                ssh_username="root",
                authentication_method=AuthenticationMethod.PRIVATE_KEY,
                sudo_mode=SudoMode.NONE,
                libvirt_uri="qemu:///system",
                status=HostStatus.READY,
                labels_json="[]",
                created_at=now,
                updated_at=now,
            )
        )
