import asyncio
import os
from pathlib import Path

import asyncssh

from nexora.remote.commands import CommandSpec
from nexora.remote.executor import RemoteCommandAudit
from nexora.remote.host_key_store import HostKeyStore
from nexora.remote.host_keys import HostKeyCandidate
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile
from nexora.remote.transfer import RemoteFileTransfer


class Server(asyncssh.SSHServer):
    def begin_auth(self, _username: str) -> bool:
        return True

    def password_auth_supported(self) -> bool:
        return True

    def validate_password(self, _username: str, password: str) -> bool:
        return password == "test-password"


class Resolver:
    def __init__(self, profile: SSHConnectionProfile) -> None:
        self.profile = profile

    def resolve(self, _host_id: str) -> SSHConnectionProfile:
        return self.profile


class Audit:
    def __init__(self) -> None:
        self.events: list[RemoteCommandAudit] = []

    def record(self, event: RemoteCommandAudit) -> None:
        self.events.append(event)


async def receive(
    process: asyncssh.SSHServerProcess[bytes],
    received: list[bytes],
) -> None:
    received.append(await process.stdin.read())
    process.exit(0)


async def run_transfer(tmp_path: Path, content: bytes) -> tuple[bytes, RemoteCommandAudit]:
    received: list[bytes] = []
    server_key = asyncssh.generate_private_key("ssh-ed25519")
    acceptor = await asyncssh.create_server(
        Server,
        "127.0.0.1",
        0,
        server_host_keys=[server_key],
        process_factory=lambda process: receive(process, received),
        encoding=None,
    )
    source = tmp_path / "source.raw"
    source.write_bytes(content)
    descriptor = os.open(source, os.O_RDONLY)
    try:
        port = acceptor.get_port()
        key_type, key_data, *_ = server_key.export_public_key("openssh").decode().split()
        store = HostKeyStore(tmp_path / "hostkeys")
        store.save("host-1", [HostKeyCandidate("127.0.0.1", port, key_type, key_data)])
        connection = SSHConnection(
            "127.0.0.1",
            port,
            "tester",
            store.path_for("host-1").absolute(),
        )
        audit = Audit()
        transfer = RemoteFileTransfer(
            Resolver(SSHConnectionProfile(connection, password="test-password")),
            audit,
        )
        result = await asyncio.to_thread(
            transfer.upload,
            "host-1",
            descriptor,
            CommandSpec("sink"),
            sudo=False,
            timeout=5,
        )
        assert 0 == result.exit_code
        assert len(content) == result.bytes_sent
        return received[0], audit.events[0]
    finally:
        os.close(descriptor)
        acceptor.close()
        await acceptor.wait_closed()


def test_remote_transfer_streams_with_host_key_and_audit(tmp_path: Path) -> None:
    content = b"nexora-transfer" * 100_000

    received, audit = asyncio.run(run_transfer(tmp_path, content))

    assert content == received
    assert "bytes_sent=" in audit.stdout_summary
