import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import asyncssh

from nexora.remote.commands import CommandSpec
from nexora.remote.executor import RemoteCommandAudit
from nexora.remote.host_key_store import HostKeyStore
from nexora.remote.host_keys import HostKeyCandidate
from nexora.remote.relay import RemoteRelayTransfer
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile


class Server(asyncssh.SSHServer):
    def begin_auth(self, _username: str) -> bool:
        return True

    def password_auth_supported(self) -> bool:
        return True

    def validate_password(self, _username: str, password: str) -> bool:
        return password == "test-password"


class Resolver:
    def __init__(self, profiles: dict[str, SSHConnectionProfile]) -> None:
        self.profiles = profiles

    def resolve(self, host_id: str) -> SSHConnectionProfile:
        return self.profiles[host_id]


class Audit:
    def __init__(self) -> None:
        self.events: list[RemoteCommandAudit] = []

    def record(self, event: RemoteCommandAudit) -> None:
        self.events.append(event)


def test_remote_relay_streams_between_strict_ssh_hosts(tmp_path: Path) -> None:
    asyncio.run(_run_relay(tmp_path))


async def _run_relay(tmp_path: Path) -> None:
    content = b"nexora-relay" * 100_000
    received: list[bytes] = []

    async def source(process: asyncssh.SSHServerProcess[bytes]) -> None:
        process.stdout.write(content)
        process.stdout.write_eof()
        process.exit(0)

    async def target(process: asyncssh.SSHServerProcess[bytes]) -> None:
        received.append(await process.stdin.read())
        process.exit(0)

    source_server, source_profile = await _server(tmp_path, "source", source)
    target_server, target_profile = await _server(tmp_path, "target", target)
    audit = Audit()
    relay = RemoteRelayTransfer(
        Resolver({"source": source_profile, "target": target_profile}),
        audit,
    )
    progress: list[int] = []
    try:
        result = await asyncio.to_thread(
            relay.copy,
            "source",
            "target",
            CommandSpec("source-reader"),
            CommandSpec("target-writer"),
            source_sudo=False,
            target_sudo=False,
            timeout=5,
            progress=progress.append,
        )
        assert (0, 0) == (result.source_exit_code, result.target_exit_code)
        assert len(content) == result.bytes_copied
        assert content == received[0]
        assert progress and len(content) == progress[-1]
        assert 2 == len(audit.events)
        assert 2 == len({event.operation_id for event in audit.events})
        assert all("bytes_" in event.stdout_summary for event in audit.events)
        assert all(result.operation_id in event.stdout_summary for event in audit.events)
    finally:
        source_server.close()
        target_server.close()
        await asyncio.gather(
            source_server.wait_closed(),
            target_server.wait_closed(),
        )


async def _server(
    tmp_path: Path,
    host_id: str,
    process_factory: Callable[[asyncssh.SSHServerProcess[bytes]], Awaitable[None]],
) -> tuple[asyncssh.SSHAcceptor, SSHConnectionProfile]:
    server_key = asyncssh.generate_private_key("ssh-ed25519")
    acceptor = await asyncssh.create_server(
        Server,
        "127.0.0.1",
        0,
        server_host_keys=[server_key],
        process_factory=process_factory,
        encoding=None,
    )
    port = acceptor.get_port()
    key_type, key_data, *_ = server_key.export_public_key("openssh").decode().split()
    store = HostKeyStore(tmp_path / "hostkeys")
    store.save(host_id, [HostKeyCandidate("127.0.0.1", port, key_type, key_data)])
    connection = SSHConnection(
        "127.0.0.1",
        port,
        "tester",
        store.path_for(host_id).absolute(),
    )
    return acceptor, SSHConnectionProfile(connection, password="test-password")
