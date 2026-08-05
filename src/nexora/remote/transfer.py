"""Audited bounded file streaming over the managed AsyncSSH connection."""

import asyncio
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

import asyncssh

from nexora.remote.async_ssh_backend import (
    asyncssh_connection_options,
)
from nexora.remote.commands import RemoteCommand, render_remote_command
from nexora.remote.executor import AuditSink, ConnectionResolver, RemoteCommandAudit
from nexora.remote.ssh import SSHConnectionProfile

TRANSFER_CHUNK_SIZE = 1024 * 1024
MAX_TRANSFER_OUTPUT = 64 * 1024
TransferProgress = Callable[[int], None]
CancellationCheck = Callable[[], bool]


@dataclass(frozen=True)
class TransferResult:
    operation_id: str
    exit_code: int
    bytes_sent: int
    stderr: bytes
    timed_out: bool
    cancelled: bool
    duration_seconds: float


class RemoteFileTransfer:
    def __init__(self, resolver: ConnectionResolver, audit_sink: AuditSink) -> None:
        self.resolver = resolver
        self.audit_sink = audit_sink

    def upload(
        self,
        host_id: str,
        source_descriptor: int,
        command: RemoteCommand,
        *,
        sudo: bool,
        timeout: int,
        progress: TransferProgress | None = None,
        cancellation_requested: CancellationCheck | None = None,
        operation_id: str | None = None,
    ) -> TransferResult:
        if not 1 <= timeout <= 86_400:
            raise ValueError("invalid transfer timeout")
        resolved_operation = operation_id or str(uuid4())
        profile = self.resolver.resolve(host_id)
        remote_command = render_remote_command(command, sudo=sudo, environment={"LC_ALL": "C"})
        result = asyncio.run(
            _upload_async(
                profile,
                source_descriptor,
                remote_command,
                timeout=timeout,
                progress=progress,
                cancellation_requested=cancellation_requested,
                operation_id=resolved_operation,
            )
        )
        self.audit_sink.record(
            RemoteCommandAudit(
                resolved_operation,
                host_id,
                render_remote_command(command, sudo=sudo, environment={"LC_ALL": "C"}),
                result.exit_code,
                result.timed_out,
                result.cancelled,
                f"bytes_sent={result.bytes_sent}",
                result.stderr[:512].decode(errors="replace"),
            )
        )
        return result


async def _upload_async(
    profile: SSHConnectionProfile,
    source_descriptor: int,
    remote_command: str,
    *,
    timeout: int,
    progress: TransferProgress | None,
    cancellation_requested: CancellationCheck | None,
    operation_id: str,
) -> TransferResult:
    started = time.monotonic()
    bytes_sent = 0
    timed_out = False
    cancelled = False
    exit_code = 255
    stderr = b""
    async with asyncssh.connect(
        profile.connection.host,
        port=profile.connection.port,
        username=profile.connection.username,
        known_hosts=str(profile.connection.known_hosts_file),
        config=None,
        agent_path=None,
        connect_timeout=min(timeout, 30),
        login_timeout=min(timeout, 30),
        **asyncssh_connection_options(profile),
    ) as connection:
        process = await connection.create_process(remote_command, encoding=None)
        stdout_task = asyncio.create_task(_read_bounded(process.stdout))
        stderr_task = asyncio.create_task(_read_bounded(process.stderr))
        try:
            async with asyncio.timeout(timeout):
                os.lseek(source_descriptor, 0, os.SEEK_SET)
                while True:
                    if cancellation_requested is not None and cancellation_requested():
                        cancelled = True
                        break
                    chunk = await asyncio.to_thread(
                        os.read,
                        source_descriptor,
                        TRANSFER_CHUNK_SIZE,
                    )
                    if not chunk:
                        break
                    process.stdin.write(chunk)
                    await process.stdin.drain()
                    bytes_sent += len(chunk)
                    if progress is not None:
                        progress(bytes_sent)
                if cancelled:
                    await _stop(process)
                else:
                    process.stdin.write_eof()
                    await process.wait_closed()
        except TimeoutError:
            timed_out = True
            await _stop(process)
        stdout = await stdout_task
        stderr = await stderr_task
        del stdout
        exit_code = process.exit_status if process.exit_status is not None else 255
    return TransferResult(
        operation_id,
        exit_code,
        bytes_sent,
        stderr,
        timed_out,
        cancelled,
        time.monotonic() - started,
    )


async def _read_bounded(reader: asyncssh.SSHReader[bytes]) -> bytes:
    output = bytearray()
    while True:
        chunk = await reader.read(64 * 1024)
        if not chunk:
            return bytes(output)
        remaining = MAX_TRANSFER_OUTPUT - len(output)
        if remaining > 0:
            output.extend(chunk[:remaining])


async def _stop(process: asyncssh.SSHClientProcess[bytes]) -> None:
    process.terminate()
    try:
        await asyncio.wait_for(process.wait_closed(), timeout=2)
    except TimeoutError:
        process.kill()
        await asyncio.wait_for(process.wait_closed(), timeout=1)
