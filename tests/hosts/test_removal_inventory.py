from pathlib import Path
from threading import Event

import pytest

from nexora.hosts.removal_inventory import (
    RemoteCleanupService,
    RemovalInventoryError,
)
from nexora.remote.executor import RemoteCommandAudit, RemoteExecutor
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile


class Resolver:
    def __init__(self, known_hosts: Path) -> None:
        self.known_hosts = known_hosts

    def resolve(self, _host_id: str) -> SSHConnectionProfile:
        return SSHConnectionProfile(SSHConnection("node", 22, "root", self.known_hosts))


class Audit:
    def record(self, _event: RemoteCommandAudit) -> None:
        return


class CleanupBackend:
    def __init__(self, *, escaped: bool = False) -> None:
        self.escaped = escaped
        self.cleaned = False
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
        if "list-units" in command:
            output = b"" if self.cleaned else b"nexora-rollback.service loaded active running\n"
        elif command.endswith("-print"):
            if self.escaped:
                output = b"/etc/nexora-escaped\n"
            else:
                output = b"" if self.cleaned else b"/tmp/nexora-operation-1\n"
        elif "systemctl stop" in command:
            output = b""
        elif command.endswith("-depth -delete"):
            self.cleaned = True
            output = b""
        else:
            raise AssertionError(command)
        return ProcessResult(0, output, b"", False, False, False, False, 0.01)


def test_inventory_only_deletes_confirmed_nexora_paths_and_units(tmp_path: Path) -> None:
    backend = CleanupBackend()
    service = _service(tmp_path, backend)

    inventory = service.discover("host-1", sudo=False)
    service.cleanup("host-1", inventory, sudo=False)
    remaining = service.discover("host-1", sudo=False)

    assert ("/tmp/nexora-operation-1",) == inventory.paths
    assert ("nexora-rollback.service",) == inventory.units
    assert () == remaining.paths
    assert () == remaining.units
    assert any(
        "find /tmp/nexora-operation-1 -xdev -depth -delete" in item for item in backend.commands
    )
    assert not any(
        command in item
        for item in backend.commands
        for command in ("virsh", "qemu-img", "nmcli", "networkctl")
    )


def test_inventory_rejects_nexora_name_outside_temporary_roots(tmp_path: Path) -> None:
    service = _service(tmp_path, CleanupBackend(escaped=True))

    with pytest.raises(RemovalInventoryError, match="allowed roots"):
        service.discover("host-1", sudo=False)


def _service(tmp_path: Path, backend: CleanupBackend) -> RemoteCleanupService:
    executor = RemoteExecutor(
        Resolver(tmp_path / "known_hosts"),
        Audit(),
        backend=backend,
    )
    return RemoteCleanupService(executor)
