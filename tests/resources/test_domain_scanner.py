from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import select

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.remote.executor import RemoteCommandAudit, RemoteExecutor
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.models import ResourceDocument, ResourceIndex, ResourceStatus

from .test_domain_discovery import DOMAIN_XML

DOMAIN_UUID = "11111111-1111-1111-1111-111111111111"


class Resolver:
    def __init__(self, known_hosts: Path) -> None:
        self.known_hosts = known_hosts

    def resolve(self, _host_id: str) -> SSHConnectionProfile:
        return SSHConnectionProfile(
            SSHConnection("host.example.test", 22, "root", self.known_hosts)
        )


class Audit:
    def record(self, _event: RemoteCommandAudit) -> None:
        return


class DomainBackend:
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
        if remote_command.endswith("list --all --uuid"):
            return _result(stdout=f"{DOMAIN_UUID}\n".encode())
        if " dominfo " in remote_command:
            return _result(
                stdout=(
                    f"Id: -\nName: existing-vm\nUUID: {DOMAIN_UUID}\n"
                    "State: shut off\nPersistent: yes\nAutostart: enable\n"
                    "Managed save: no\n"
                ).encode()
            )
        if " dumpxml --inactive " in remote_command:
            return _result(stdout=DOMAIN_XML)
        if " snapshot-list " in remote_command:
            return _result(stdout=b"before-upgrade\n")
        raise AssertionError(remote_command)


@pytest.fixture
def scanner_runtime(
    settings: Settings,
) -> Iterator[tuple[Database, DomainDiscoveryService]]:
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    executor = RemoteExecutor(
        Resolver(settings.data_dir / "hostkeys" / "known_hosts"),
        Audit(),
        backend=DomainBackend(),
    )
    try:
        yield database, DomainDiscoveryService(database, executor)
    finally:
        database.dispose()


def test_scanner_indexes_existing_domain_without_import(
    scanner_runtime: tuple[Database, DomainDiscoveryService],
) -> None:
    database, scanner = scanner_runtime
    progress: list[tuple[float, str]] = []

    result = scanner.run(
        "host-1",
        progress=lambda percentage, message: progress.append((percentage, message)),
    )

    assert 1 == result.generation
    assert 100 == progress[-1][0]
    with database.session() as session:
        resource = session.scalar(select(ResourceIndex))
        document = session.scalar(select(ResourceDocument))
        assert resource is not None
        assert "existing-vm" == resource.display_name
        assert ResourceStatus.MANAGED == resource.status
        assert '"snapshot_names":["before-upgrade"]' in resource.details_json
        assert document is not None
        assert DOMAIN_XML == document.content


def _add_host(database: Database) -> None:
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(
            Host(
                id="host-1",
                name="node-one",
                address="node-one.example.test",
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


def _result(*, stdout: bytes = b"") -> ProcessResult:
    return ProcessResult(0, stdout, b"", False, False, False, False, 0.01)
