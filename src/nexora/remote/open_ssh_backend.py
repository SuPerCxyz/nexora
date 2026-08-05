"""OpenSSH subprocess backend for key-file based integrations."""

from threading import Event
from typing import Protocol

from nexora.remote.process import BoundedProcessRunner, ProcessResult
from nexora.remote.ssh import SSHConnectionProfile, build_ssh_argv_for_text


class SubprocessRunner(Protocol):
    def run(
        self,
        argv: list[str],
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult: ...


class OpenSSHBackend:
    """Retain the audited P0 subprocess path for non-secret key files."""

    def __init__(self, process_runner: SubprocessRunner | None = None) -> None:
        self.process_runner = process_runner or BoundedProcessRunner()

    def run(
        self,
        profile: SSHConnectionProfile,
        remote_command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult:
        if profile.password or profile.private_key or profile.private_key_passphrase:
            raise ValueError("OpenSSH backend does not accept in-memory credentials")

        argv = build_ssh_argv_for_text(profile.connection, remote_command)
        return self.process_runner.run(
            argv,
            timeout=timeout,
            stdin=stdin,
            cancel_event=cancel_event,
        )
