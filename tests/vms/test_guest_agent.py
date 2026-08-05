import json
from datetime import UTC, datetime

from sqlalchemy import select

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.remote.executor import CommandResult
from nexora.resources.models import (
    ResourceDocument,
    ResourceIndex,
    ResourceStatus,
    ResourceType,
)
from nexora.vms.guest_agent import GuestAgentService

VM_UUID = "22222222-2222-2222-2222-222222222222"


class Executor:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.commands: list[tuple[str, ...]] = []

    def run(self, _host_id: str, command: object, **_kwargs: object) -> CommandResult:
        argv = command.argv()  # type: ignore[attr-defined]
        self.commands.append(argv)
        execute = json.loads(argv[5])["execute"]
        payload: object
        if not self.available:
            return _result(1, b"", b"agent unavailable")
        if execute == "guest-ping":
            payload = {"return": {}}
        elif execute == "guest-get-host-name":
            payload = {"return": {"host-name": "guest.example.test"}}
        else:
            payload = {
                "return": [
                    {
                        "name": "eth0",
                        "hardware-address": "52:54:00:12:34:56",
                        "ip-addresses": [
                            {
                                "ip-address": "192.0.2.10",
                                "ip-address-type": "ipv4",
                                "prefix": 24,
                            },
                            {
                                "ip-address": "127.0.0.1",
                                "ip-address-type": "ipv4",
                                "prefix": 8,
                            },
                        ],
                    }
                ]
            }
        return _result(0, json.dumps(payload).encode(), b"")


def test_guest_agent_connected_returns_bounded_hostname_and_addresses(
    settings: Settings,
) -> None:
    database = _database(settings, channel=True, state="running")
    executor = Executor()
    view = GuestAgentService(database, executor).read("host-1", VM_UUID)  # type: ignore[arg-type]
    assert "connected" == view.state
    assert "guest.example.test" == view.hostname
    assert 1 == len(view.addresses)
    assert "192.0.2.10" == view.addresses[0].address
    assert all("qemu-agent-command" in command for command in executor.commands)
    database.dispose()


def test_guest_agent_reports_channel_and_runtime_boundaries(settings: Settings) -> None:
    no_channel = _database(settings, channel=False, state="running")
    executor = Executor()
    assert (
        "not_configured"
        == GuestAgentService(no_channel, executor)
        .read(  # type: ignore[arg-type]
            "host-1", VM_UUID
        )
        .state
    )
    assert [] == executor.commands

    with no_channel.session() as session:
        resource = session.get(ResourceIndex, "vm-1")
        document = session.scalar(select(ResourceDocument))
        assert resource is not None
        assert document is not None
        resource.details_json = json.dumps({"state": "shut off", "persistent": True})
        document.content = document.content.replace(
            b"<devices>",
            (
                b"<devices><channel type='unix'><target type='virtio' "
                b"name='org.qemu.guest_agent.0'/></channel>"
            ),
        )
    stopped = no_channel
    executor = Executor()
    assert (
        "stopped"
        == GuestAgentService(stopped, executor)
        .read(  # type: ignore[arg-type]
            "host-1", VM_UUID
        )
        .state
    )
    assert [] == executor.commands
    stopped.dispose()


def test_guest_agent_failure_degrades_without_exposing_stderr(settings: Settings) -> None:
    database = _database(settings, channel=True, state="running")
    view = GuestAgentService(database, Executor(available=False)).read(  # type: ignore[arg-type]
        "host-1", VM_UUID
    )
    assert "unavailable" == view.state
    assert view.message is not None
    assert "stderr" not in view.message
    database.dispose()


def _database(settings: Settings, *, channel: bool, state: str) -> Database:
    database = Database(settings)
    upgrade_database(database)
    now = datetime.now(UTC)
    channel_xml = (
        "<channel type='unix'><target type='virtio' name='org.qemu.guest_agent.0'/></channel>"
        if channel
        else ""
    )
    xml = (
        f"<domain type='kvm'><name>guest</name><uuid>{VM_UUID}</uuid>"
        f"<memory unit='KiB'>524288</memory><vcpu>1</vcpu><devices>{channel_xml}"
        "</devices></domain>"
    ).encode()
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
        session.flush()
        session.add(
            ResourceIndex(
                id="vm-1",
                host_id="host-1",
                resource_type=ResourceType.VIRTUAL_MACHINE,
                native_id=VM_UUID,
                display_name="guest",
                status=ResourceStatus.MANAGED,
                source="existing",
                persistent_hash="a" * 64,
                live_hash="b" * 64 if state == "running" else None,
                observed_generation=1,
                details_json=json.dumps({"state": state, "persistent": True}),
                labels_json="[]",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        session.flush()
        session.add(
            ResourceDocument(
                resource_index_id="vm-1",
                document_kind="persistent_xml",
                content=xml,
                content_hash="a" * 64,
                hash_algorithm="sha256",
                observed_at=now,
            )
        )
    return database


def _result(exit_code: int, stdout: bytes, stderr: bytes) -> CommandResult:
    return CommandResult(
        "operation",
        exit_code,
        stdout,
        stderr,
        False,
        False,
        False,
        False,
        0.01,
    )
