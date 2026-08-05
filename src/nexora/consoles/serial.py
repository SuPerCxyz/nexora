"""Strict AsyncSSH transport for an interactive libvirt serial console."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import asyncssh

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.async_ssh_backend import asyncssh_connection_options
from nexora.remote.commands import CommandSpec, render_remote_command
from nexora.remote.executor import ConnectionResolver

READ_SIZE = 64 * 1024


class SerialConsoleConnection:
    def __init__(
        self,
        connection: asyncssh.SSHClientConnection,
        process: asyncssh.SSHClientProcess[bytes],
    ) -> None:
        self.connection = connection
        self.process = process

    async def read(self) -> bytes:
        return await self.process.stdout.read(READ_SIZE)

    def write(self, data: bytes) -> None:
        self.process.stdin.write(data)

    async def close(self) -> None:
        self.process.stdin.write_eof()
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait_closed(), timeout=2)
        except TimeoutError:
            self.process.kill()
        self.connection.close()
        await self.connection.wait_closed()


class SerialConsoleConnector:
    def __init__(self, database: Database, resolver: ConnectionResolver) -> None:
        self.database = database
        self.resolver = resolver

    @asynccontextmanager
    async def open(
        self,
        host_id: str,
        vm_uuid: str,
    ) -> AsyncIterator[SerialConsoleConnection]:
        host = await asyncio.to_thread(self._host, host_id)
        profile = await asyncio.to_thread(self.resolver.resolve, host_id)
        command = render_remote_command(
            CommandSpec(
                "virsh",
                (
                    "-c",
                    host.libvirt_uri,
                    "console",
                    str(UUID(vm_uuid)),
                    "--safe",
                ),
            ),
            sudo=host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS,
            environment={"LC_ALL": "C"},
        )
        connection = await asyncssh.connect(
            profile.connection.host,
            port=profile.connection.port,
            username=profile.connection.username,
            known_hosts=str(profile.connection.known_hosts_file),
            config=None,
            agent_path=None,
            connect_timeout=15,
            login_timeout=15,
            **asyncssh_connection_options(profile),
        )
        process = await connection.create_process(
            command,
            term_type="xterm-256color",
            term_size=(80, 24),
            encoding=None,
        )
        console = SerialConsoleConnection(connection, process)
        try:
            yield console
        finally:
            await console.close()

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise ValueError("host not found")
            session.expunge(host)
            return host
