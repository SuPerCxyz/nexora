"""Audited remote-to-remote streaming without local file persistence."""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4, uuid5

import asyncssh

from nexora.remote.async_ssh_backend import asyncssh_connection_options
from nexora.remote.commands import RemoteCommand, render_remote_command
from nexora.remote.executor import AuditSink, ConnectionResolver, RemoteCommandAudit
from nexora.remote.ssh import SSHConnectionProfile
from nexora.remote.transfer import MAX_TRANSFER_OUTPUT, TRANSFER_CHUNK_SIZE

RelayProgress = Callable[[int], None]
CancellationCheck = Callable[[], bool]


@dataclass(frozen=True)
class RelayResult:
    operation_id: str
    source_exit_code: int
    target_exit_code: int
    bytes_copied: int
    source_stderr: bytes
    target_stderr: bytes
    timed_out: bool
    cancelled: bool
    duration_seconds: float


class RemoteRelayTransfer:
    def __init__(self, resolver: ConnectionResolver, audit_sink: AuditSink) -> None:
        self.resolver = resolver
        self.audit_sink = audit_sink

    def copy(
        self,
        source_host_id: str,
        target_host_id: str,
        source_command: RemoteCommand,
        target_command: RemoteCommand,
        *,
        source_sudo: bool,
        target_sudo: bool,
        timeout: int,
        progress: RelayProgress | None = None,
        cancellation_requested: CancellationCheck | None = None,
        operation_id: str | None = None,
    ) -> RelayResult:
        if not 1 <= timeout <= 86_400:
            raise ValueError("invalid transfer timeout")
        operation = operation_id or str(uuid4())
        source_profile = self.resolver.resolve(source_host_id)
        target_profile = self.resolver.resolve(target_host_id)
        source_rendered = render_remote_command(
            source_command,
            sudo=source_sudo,
            environment={"LC_ALL": "C"},
        )
        target_rendered = render_remote_command(
            target_command,
            sudo=target_sudo,
            environment={"LC_ALL": "C"},
        )
        result = asyncio.run(
            _copy_async(
                source_profile,
                target_profile,
                source_rendered,
                target_rendered,
                timeout=timeout,
                progress=progress,
                cancellation_requested=cancellation_requested,
                operation_id=operation,
            )
        )
        self._audit(source_host_id, source_rendered, result, source=True)
        self._audit(target_host_id, target_rendered, result, source=False)
        return result

    def _audit(
        self,
        host_id: str,
        command: str,
        result: RelayResult,
        *,
        source: bool,
    ) -> None:
        direction = "source" if source else "target"
        audit_operation_id = str(uuid5(UUID(result.operation_id), direction))
        self.audit_sink.record(
            RemoteCommandAudit(
                audit_operation_id,
                host_id,
                command,
                result.source_exit_code if source else result.target_exit_code,
                result.timed_out,
                result.cancelled,
                (
                    f"relay_operation={result.operation_id} "
                    f"bytes_{'read' if source else 'written'}={result.bytes_copied}"
                ),
                (result.source_stderr if source else result.target_stderr)[:512].decode(
                    errors="replace"
                ),
            )
        )


async def _copy_async(
    source_profile: SSHConnectionProfile,
    target_profile: SSHConnectionProfile,
    source_command: str,
    target_command: str,
    *,
    timeout: int,
    progress: RelayProgress | None,
    cancellation_requested: CancellationCheck | None,
    operation_id: str,
) -> RelayResult:
    started = time.monotonic()
    copied = 0
    timed_out = False
    cancelled = False
    async with (
        _connection(source_profile, timeout) as source_connection,
        _connection(target_profile, timeout) as target_connection,
    ):
        source = await source_connection.create_process(source_command, encoding=None)
        target = await target_connection.create_process(target_command, encoding=None)
        source_error = asyncio.create_task(_read_bounded(source.stderr))
        target_error = asyncio.create_task(_read_bounded(target.stderr))
        try:
            async with asyncio.timeout(timeout):
                while chunk := await source.stdout.read(TRANSFER_CHUNK_SIZE):
                    if cancellation_requested is not None and cancellation_requested():
                        cancelled = True
                        break
                    target.stdin.write(chunk)
                    await target.stdin.drain()
                    copied += len(chunk)
                    if progress is not None:
                        progress(copied)
                if cancelled:
                    await asyncio.gather(_stop(source), _stop(target))
                else:
                    target.stdin.write_eof()
                    await asyncio.gather(source.wait_closed(), target.wait_closed())
        except TimeoutError:
            timed_out = True
            await asyncio.gather(_stop(source), _stop(target))
        source_stderr, target_stderr = await asyncio.gather(source_error, target_error)
        source_exit = source.exit_status if source.exit_status is not None else 255
        target_exit = target.exit_status if target.exit_status is not None else 255
    return RelayResult(
        operation_id,
        source_exit,
        target_exit,
        copied,
        source_stderr,
        target_stderr,
        timed_out,
        cancelled,
        time.monotonic() - started,
    )


@asynccontextmanager
async def _connection(
    profile: SSHConnectionProfile,
    timeout: int,
) -> AsyncIterator[asyncssh.SSHClientConnection]:
    connection = await asyncssh.connect(
        profile.connection.host,
        port=profile.connection.port,
        username=profile.connection.username,
        known_hosts=str(profile.connection.known_hosts_file),
        config=None,
        agent_path=None,
        connect_timeout=min(timeout, 30),
        login_timeout=min(timeout, 30),
        **asyncssh_connection_options(profile),
    )
    try:
        yield connection
    finally:
        connection.close()
        await connection.wait_closed()


async def _read_bounded(reader: asyncssh.SSHReader[bytes]) -> bytes:
    output = bytearray()
    while chunk := await reader.read(64 * 1024):
        remaining = MAX_TRANSFER_OUTPUT - len(output)
        if remaining > 0:
            output.extend(chunk[:remaining])
    return bytes(output)


async def _stop(process: asyncssh.SSHClientProcess[bytes]) -> None:
    process.terminate()
    try:
        await asyncio.wait_for(process.wait_closed(), timeout=2)
    except TimeoutError:
        process.kill()
        await asyncio.wait_for(process.wait_closed(), timeout=1)
