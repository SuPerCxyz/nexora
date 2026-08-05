import asyncio
from collections.abc import Callable
from pathlib import Path

import asyncssh

from nexora.remote.async_ssh_backend import AsyncSSHBackend
from nexora.remote.host_key_store import HostKeyStore
from nexora.remote.host_keys import HostKeyCandidate
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile


class _TestServer(asyncssh.SSHServer):
    def __init__(self, client_key: bytes | None = None) -> None:
        self.client_key = client_key

    def begin_auth(self, _username: str) -> bool:
        return True

    def password_auth_supported(self) -> bool:
        return self.client_key is None

    def validate_password(self, _username: str, password: str) -> bool:
        return password == "test-password"

    def public_key_auth_supported(self) -> bool:
        return self.client_key is not None

    def validate_public_key(self, _username: str, key: asyncssh.SSHKey) -> bool:
        return self.client_key is not None and key.export_public_key("openssh") == self.client_key


async def _process(process: asyncssh.SSHServerProcess[bytes]) -> None:
    if process.command == "slow":
        await asyncio.sleep(10)
        process.exit(0)
        return
    stdin = await process.stdin.read()
    process.stdout.write(process.command.encode() + b":" + stdin)
    process.exit(0)


async def _run_with_server(
    tmp_path: Path,
    profile_factory: Callable[[SSHConnection], SSHConnectionProfile],
    *,
    client_key: bytes | None = None,
    output_limit: int = 1024,
    command: str = "probe",
    timeout: int = 5,
) -> ProcessResult:
    server_key = asyncssh.generate_private_key("ssh-ed25519")
    acceptor = await asyncssh.create_server(
        lambda: _TestServer(client_key),
        "127.0.0.1",
        0,
        server_host_keys=[server_key],
        process_factory=_process,
        encoding=None,
    )
    try:
        port = acceptor.get_port()
        key_type, key_data, *_ = server_key.export_public_key("openssh").decode().split()
        store = HostKeyStore(tmp_path / "hostkeys")
        store.save(
            "host-1",
            [HostKeyCandidate("127.0.0.1", port, key_type, key_data)],
        )
        connection = SSHConnection(
            "127.0.0.1",
            port,
            "tester",
            store.path_for("host-1").absolute(),
        )
        backend = AsyncSSHBackend(max_output_bytes=output_limit)
        result = await asyncio.to_thread(
            backend.run,
            profile_factory(connection),
            command,
            timeout=timeout,
            stdin=b"input",
            cancel_event=None,
        )
        return result
    finally:
        acceptor.close()
        await acceptor.wait_closed()


def test_async_backend_supports_password_and_bounded_output(tmp_path: Path) -> None:
    result = asyncio.run(
        _run_with_server(
            tmp_path,
            lambda connection: SSHConnectionProfile(
                connection,
                password="test-password",
            ),
            output_limit=5,
        )
    )

    assert b"probe" == result.stdout
    assert result.stdout_truncated is True


def test_async_backend_supports_encrypted_in_memory_private_key(tmp_path: Path) -> None:
    client_key = asyncssh.generate_private_key("ssh-ed25519")
    private_key = client_key.export_private_key("openssh", passphrase="key-passphrase").decode()
    result = asyncio.run(
        _run_with_server(
            tmp_path,
            lambda connection: SSHConnectionProfile(
                connection,
                private_key=private_key,
                private_key_passphrase="key-passphrase",
            ),
            client_key=client_key.export_public_key("openssh"),
        )
    )

    assert b"probe:input" == result.stdout
    assert result.stdout_truncated is False


def test_async_backend_terminates_timed_out_command(tmp_path: Path) -> None:
    result = asyncio.run(
        _run_with_server(
            tmp_path,
            lambda connection: SSHConnectionProfile(
                connection,
                password="test-password",
            ),
            command="slow",
            timeout=1,
        )
    )

    assert result.timed_out is True
    assert result.exit_code != 0
