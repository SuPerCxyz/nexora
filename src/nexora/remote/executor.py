"""Unified audited remote command execution."""

from dataclasses import dataclass
from threading import Event
from typing import Protocol
from uuid import uuid4

from nexora.remote.commands import RemoteCommand, render_remote_command
from nexora.remote.open_ssh_backend import OpenSSHBackend, SubprocessRunner
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnectionProfile


class ConnectionResolver(Protocol):
    def resolve(self, host_id: str) -> SSHConnectionProfile: ...


@dataclass(frozen=True)
class RemoteCommandAudit:
    operation_id: str
    host_id: str
    command_summary: str
    exit_code: int
    timed_out: bool
    cancelled: bool
    stdout_summary: str
    stderr_summary: str


class AuditSink(Protocol):
    def record(self, event: RemoteCommandAudit) -> None: ...


class SSHBackend(Protocol):
    def run(
        self,
        profile: SSHConnectionProfile,
        remote_command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult: ...


@dataclass(frozen=True)
class CommandResult:
    operation_id: str
    exit_code: int
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool
    cancelled: bool
    duration_seconds: float


class RemoteExecutor:
    """Resolve a host, execute strict SSH, and emit a redacted audit event."""

    def __init__(
        self,
        resolver: ConnectionResolver,
        audit_sink: AuditSink,
        *,
        process_runner: SubprocessRunner | None = None,
        backend: SSHBackend | None = None,
    ) -> None:
        if process_runner is not None and backend is not None:
            raise ValueError("select either process_runner or backend")
        self.resolver = resolver
        self.audit_sink = audit_sink
        self.backend = backend or OpenSSHBackend(process_runner)

    def run(
        self,
        host_id: str,
        command: RemoteCommand,
        *,
        sudo: bool = False,
        timeout: int = 30,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
        sensitive: bool = False,
        operation_id: str | None = None,
        cancel_event: Event | None = None,
    ) -> CommandResult:
        resolved_operation_id = operation_id or str(uuid4())
        profile = self.resolver.resolve(host_id)
        remote_command = render_remote_command(command, sudo=sudo, environment=env)
        process = self.backend.run(
            profile,
            remote_command,
            timeout=timeout,
            stdin=stdin,
            cancel_event=cancel_event,
        )
        self._audit(
            host_id,
            command,
            process,
            operation_id=resolved_operation_id,
            sudo=sudo,
            environment=env,
            sensitive=sensitive,
        )
        return CommandResult(resolved_operation_id, **vars(process))

    def _audit(
        self,
        host_id: str,
        command: RemoteCommand,
        process: ProcessResult,
        *,
        operation_id: str,
        sudo: bool,
        environment: dict[str, str] | None,
        sensitive: bool,
    ) -> None:
        summary = (
            "[sensitive command]"
            if sensitive
            else render_remote_command(command, sudo=sudo, environment=environment)
        )
        stdout = "" if sensitive else _summary(process.stdout)
        stderr = "" if sensitive else _summary(process.stderr)
        self.audit_sink.record(
            RemoteCommandAudit(
                operation_id,
                host_id,
                summary,
                process.exit_code,
                process.timed_out,
                process.cancelled,
                stdout,
                stderr,
            )
        )


def _summary(output: bytes) -> str:
    return output[:512].decode("utf-8", errors="replace")
