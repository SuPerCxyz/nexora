from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import func, select

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import (
    AuthenticationMethod,
    Host,
    HostCapability,
    HostStatus,
    SudoMode,
)
from nexora.hosts.probe import HostProbeService
from nexora.remote.executor import RemoteCommandAudit, RemoteExecutor
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile


class Resolver:
    def __init__(self, known_hosts: Path) -> None:
        self.known_hosts = known_hosts

    def resolve(self, _host_id: str) -> SSHConnectionProfile:
        return SSHConnectionProfile(
            SSHConnection("host.example.test", 22, "root", self.known_hosts.absolute())
        )


class Audit:
    def record(self, _event: RemoteCommandAudit) -> None:
        return


class ProbeBackend:
    def run(
        self,
        _profile: SSHConnectionProfile,
        remote_command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult:
        del timeout, stdin, cancel_event
        if "command -v virsh" in remote_command:
            return _result(stdout=b"/usr/bin/virsh\n")
        if "command -v" in remote_command:
            return _result(exit_code=1)
        if remote_command.endswith("id -u"):
            return _result(stdout=b"0\n")
        if remote_command.endswith("uname -srm"):
            return _result(stdout=b"Linux 6.12 x86_64\n")
        if remote_command.endswith("cat /etc/os-release"):
            return _result(stdout=b'ID=debian\nVERSION_ID="13"\n')
        if remote_command.endswith("lscpu -J"):
            return _result(
                stdout=b'{"lscpu":[{"field":"Architecture:","data":"x86_64"},'
                b'{"field":"CPU(s):","data":"16"},'
                b'{"field":"Model name:","data":"Example CPU"}]}'
            )
        if remote_command.endswith("cat /sys/class/dmi/id/sys_vendor"):
            return _result(stdout=b"Example Vendor\n")
        if remote_command.endswith("cat /sys/class/dmi/id/product_name"):
            return _result(stdout=b"Example Server\n")
        if remote_command.endswith("virsh -c qemu:///system version"):
            return _result(stdout=b"Using library: libvirt 11.0.0\n")
        if remote_command.endswith("virsh -c qemu:///system nodeinfo"):
            return _result(stdout=b"CPU(s): 16\nMemory size: 32768000 KiB\n")
        if remote_command.endswith("virsh -c qemu:///system list --all --uuid"):
            return _result(stdout=b"11111111-1111-1111-1111-111111111111\n")
        raise AssertionError(remote_command)


class PasswordlessToolBackend(ProbeBackend):
    """Tool discovery must not wrap shell builtins with env on any user."""

    def run(
        self,
        profile: SSHConnectionProfile,
        remote_command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult:
        if "command -v" in remote_command:
            assert "env" not in remote_command, remote_command
            return _result(stdout=b"/usr/bin/virsh\n")
        return super().run(
            profile, remote_command, timeout=timeout, stdin=stdin, cancel_event=cancel_event
        )


@pytest.fixture
def probe_runtime(settings: Settings) -> Iterator[tuple[Database, HostProbeService, Host]]:
    database = Database(settings)
    upgrade_database(database)
    host = _host()
    with database.session() as session:
        session.add(host)
    executor = RemoteExecutor(
        Resolver(settings.data_dir / "hostkeys" / "host.known_hosts"),
        Audit(),
        backend=ProbeBackend(),
    )
    try:
        yield database, HostProbeService(database, executor), host
    finally:
        database.dispose()


def test_probe_persists_system_libvirt_tools_and_existing_vm_ids(
    probe_runtime: tuple[Database, HostProbeService, Host],
) -> None:
    database, probe, host = probe_runtime
    progress: list[tuple[int, int, str]] = []

    report = probe.run(
        host.id, progress=lambda step, total, name: progress.append((step, total, name))
    )

    assert report.healthy is True
    assert (22, 22, "libvirt.domain_uuids") == progress[-1]
    capabilities = {item.key: item for item in report.observations}
    assert ["11111111-1111-1111-1111-111111111111"] == capabilities["libvirt.domain_uuids"].value
    assert "Example CPU" == capabilities["system.lscpu"].value["model_name"]
    assert "Example Vendor" == capabilities["system.manufacturer"].value
    assert "optional_missing" == capabilities["tool.nmcli"].status
    with database.session() as session:
        stored = session.get(Host, host.id)
        count = session.scalar(
            select(func.count())
            .select_from(HostCapability)
            .where(HostCapability.host_id == host.id)
        )
        assert stored is not None
        assert HostStatus.READY == stored.status
        assert 22 == count


def test_probe_uses_sudo_path_for_tools_on_passwordless_sudo_host(
    settings: Settings,
) -> None:
    database = Database(settings)
    upgrade_database(database)
    with database.session() as session:
        session.add(_host(ssh_username="ubuntu", sudo_mode=SudoMode.PASSWORDLESS))
    executor = RemoteExecutor(
        Resolver(settings.data_dir / "hostkeys" / "host.known_hosts"),
        Audit(),
        backend=PasswordlessToolBackend(),
    )
    probe = HostProbeService(database, executor)
    try:
        report = probe.run("host-1")
    finally:
        database.dispose()

    assert report.healthy is True
    capabilities = {item.key: item for item in report.observations}
    assert "normal" == capabilities["tool.virsh"].status


def _host(
    *,
    ssh_username: str = "root",
    sudo_mode: SudoMode = SudoMode.NONE,
) -> Host:
    now = datetime.now(UTC)
    return Host(
        id="host-1",
        name="node-one",
        address="host.example.test",
        ssh_port=22,
        ssh_username=ssh_username,
        authentication_method=AuthenticationMethod.PRIVATE_KEY,
        sudo_mode=sudo_mode,
        libvirt_uri="qemu:///system",
        status=HostStatus.READY,
        labels_json="[]",
        created_at=now,
        updated_at=now,
    )


def _result(*, exit_code: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> ProcessResult:
    return ProcessResult(exit_code, stdout, stderr, False, False, False, False, 0.01)
