"""Strict OpenSSH process arguments."""

import re
from dataclasses import dataclass
from pathlib import Path

from nexora.remote.commands import RemoteCommand, render_remote_command
from nexora.remote.validation import validate_host, validate_port

USERNAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")


@dataclass(frozen=True)
class SSHConnection:
    """Connection material resolved from a managed host."""

    host: str
    port: int
    username: str
    known_hosts_file: Path
    identity_file: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "host", validate_host(self.host))
        object.__setattr__(self, "port", validate_port(self.port))
        if not USERNAME_PATTERN.fullmatch(self.username):
            raise ValueError("invalid SSH username")
        if not self.known_hosts_file.is_absolute():
            raise ValueError("known_hosts path must be absolute")
        if self.identity_file is not None and not self.identity_file.is_absolute():
            raise ValueError("identity path must be absolute")


@dataclass(frozen=True)
class SSHConnectionProfile:
    """A strict target plus one in-memory authentication mechanism."""

    connection: SSHConnection
    password: str | None = None
    private_key: str | None = None
    private_key_passphrase: str | None = None

    def __post_init__(self) -> None:
        if self.password and self.private_key:
            raise ValueError("SSH profile cannot mix password and private key")
        if self.private_key_passphrase and not self.private_key:
            raise ValueError("SSH key passphrase requires a private key")


def build_ssh_argv(
    connection: SSHConnection,
    command: RemoteCommand,
    *,
    sudo: bool = False,
    environment: dict[str, str] | None = None,
) -> list[str]:
    """Build an isolated, non-interactive OpenSSH invocation."""

    remote_command = render_remote_command(command, sudo=sudo, environment=environment)
    return build_ssh_argv_for_text(connection, remote_command)


def build_ssh_argv_for_text(
    connection: SSHConnection,
    remote_command: str,
) -> list[str]:
    """Build strict SSH argv for a command already rendered from typed argv."""

    argv = [
        "ssh",
        "-F",
        "/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={connection.known_hosts_file}",
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "UpdateHostKeys=no",
        "-o",
        "PermitLocalCommand=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-p",
        str(connection.port),
        "-l",
        connection.username,
    ]
    if connection.identity_file is not None:
        argv.extend(("-i", str(connection.identity_file)))
    argv.extend(
        (
            "--",
            connection.host,
            remote_command,
        )
    )
    return argv
