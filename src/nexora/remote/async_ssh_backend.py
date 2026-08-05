"""AsyncSSH backend with strict trust and bounded streaming output."""

import asyncio
import time
from dataclasses import dataclass
from threading import Event

import asyncssh

from nexora.remote.process import MAX_STDIN_BYTES, ProcessResult
from nexora.remote.ssh import SSHConnectionProfile

READ_SIZE = 64 * 1024


@dataclass(frozen=True)
class _ControlResult:
    timed_out: bool
    cancelled: bool


class AsyncSSHBackend:
    """Run password or in-memory key authentication without ambient SSH config."""

    def __init__(self, *, max_output_bytes: int = 4 * 1024 * 1024) -> None:
        if not 1 <= max_output_bytes <= 64 * 1024 * 1024:
            raise ValueError("invalid output limit")
        self.max_output_bytes = max_output_bytes

    def run(
        self,
        profile: SSHConnectionProfile,
        remote_command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult:
        if not 1 <= timeout <= 86_400:
            raise ValueError("invalid command timeout")
        if stdin is not None and len(stdin) > MAX_STDIN_BYTES:
            raise ValueError("stdin exceeded limit")
        return asyncio.run(
            self._run_async(
                profile,
                remote_command,
                timeout=timeout,
                stdin=stdin,
                cancel_event=cancel_event,
            )
        )

    async def _run_async(
        self,
        profile: SSHConnectionProfile,
        remote_command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult:
        started = time.monotonic()
        options = asyncssh_connection_options(profile)
        async with asyncssh.connect(
            profile.connection.host,
            port=profile.connection.port,
            username=profile.connection.username,
            known_hosts=str(profile.connection.known_hosts_file),
            config=None,
            agent_path=None,
            connect_timeout=min(timeout, 30),
            login_timeout=min(timeout, 30),
            **options,
        ) as connection:
            process = await connection.create_process(remote_command, encoding=None)
            if stdin is not None:
                process.stdin.write(stdin)
            process.stdin.write_eof()
            stdout_task = asyncio.create_task(_read_bounded(process.stdout, self.max_output_bytes))
            stderr_task = asyncio.create_task(_read_bounded(process.stderr, self.max_output_bytes))
            control = await _control_process(process, timeout, cancel_event)
            stdout, stdout_truncated = await stdout_task
            stderr, stderr_truncated = await stderr_task
            exit_code = process.exit_status if process.exit_status is not None else 255
        return ProcessResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            timed_out=control.timed_out,
            cancelled=control.cancelled,
            duration_seconds=time.monotonic() - started,
        )


def asyncssh_connection_options(profile: SSHConnectionProfile) -> dict[str, object]:
    if profile.password is not None:
        return {"password": profile.password, "client_keys": []}
    if profile.private_key is not None:
        return {
            "client_keys": [profile.private_key.encode()],
            "passphrase": profile.private_key_passphrase,
        }
    if profile.connection.identity_file is not None:
        return {"client_keys": [str(profile.connection.identity_file)]}
    return {"client_keys": []}


async def _read_bounded(
    reader: asyncssh.SSHReader[bytes],
    limit: int,
) -> tuple[bytes, bool]:
    buffer = bytearray()
    truncated = False
    while True:
        chunk = await reader.read(READ_SIZE)
        if not chunk:
            return bytes(buffer), truncated
        remaining = limit - len(buffer)
        if remaining > 0:
            buffer.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated = True


async def _control_process(
    process: asyncssh.SSHClientProcess[bytes],
    timeout: int,
    cancel_event: Event | None,
) -> _ControlResult:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while process.exit_status is None:
        if cancel_event is not None and cancel_event.is_set():
            await _stop_process(process)
            return _ControlResult(timed_out=False, cancelled=True)
        if loop.time() >= deadline:
            await _stop_process(process)
            return _ControlResult(timed_out=True, cancelled=False)
        await asyncio.sleep(0.05)
    await process.wait_closed()
    return _ControlResult(timed_out=False, cancelled=False)


async def _stop_process(process: asyncssh.SSHClientProcess[bytes]) -> None:
    process.terminate()
    try:
        await asyncio.wait_for(process.wait_closed(), timeout=2)
    except TimeoutError:
        process.kill()
        try:
            await asyncio.wait_for(process.wait_closed(), timeout=1)
        except TimeoutError:
            process.close()
