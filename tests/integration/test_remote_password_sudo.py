"""Real password SSH and passwordless sudo compatibility test."""

import os
import secrets
from pathlib import Path

import pytest

from nexora.remote.async_ssh_backend import AsyncSSHBackend
from nexora.remote.commands import CommandSpec, render_remote_command
from nexora.remote.executor import RemoteCommandAudit, RemoteExecutor
from nexora.remote.host_key_scanner import scan_host_keys
from nexora.remote.host_key_store import HostKeyStore
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="dedicated remote KVM integration environment is not configured",
)
TEST_USER = "nexora-it-password"
SUDOERS = f"/etc/sudoers.d/{TEST_USER}"
SETUP = f"""set -Eeuo pipefail
getent passwd {TEST_USER} >/dev/null && exit 73
test ! -e {SUDOERS} || exit 74
read -r nexora_password
trap 'rm -f {SUDOERS}; userdel --force {TEST_USER} 2>/dev/null || true' ERR
useradd --no-create-home --shell /bin/bash {TEST_USER}
printf '{TEST_USER}:%s\\n' "$nexora_password" | chpasswd
printf '{TEST_USER} ALL=(ALL) NOPASSWD: ALL\\n' > {SUDOERS}
chmod 0440 {SUDOERS}
visudo -cf {SUDOERS} >/dev/null
trap - ERR
"""
CLEANUP = f"""set -eu
rm -f {SUDOERS}
pkill -u {TEST_USER} 2>/dev/null || true
userdel --force {TEST_USER} 2>/dev/null || true
"""


class _Resolver:
    def __init__(self, profile: SSHConnectionProfile) -> None:
        self.profile = profile

    def resolve(self, _host_id: str) -> SSHConnectionProfile:
        return self.profile


class _Audit:
    def __init__(self) -> None:
        self.events: list[RemoteCommandAudit] = []

    def record(self, event: RemoteCommandAudit) -> None:
        self.events.append(event)


def test_real_password_ssh_and_passwordless_sudo(tmp_path: Path) -> None:
    host = HOST or ""
    known_hosts = HostKeyStore(tmp_path / "hostkeys").save(
        "password-sudo",
        scan_host_keys(host, 22),
    )
    root = SSHConnectionProfile(
        SSHConnection(host, 22, "root", known_hosts),
        private_key=Path(KEY_FILE or "").read_text(),
    )
    backend = AsyncSSHBackend()
    password = secrets.token_urlsafe(24)
    setup = render_remote_command(CommandSpec("bash", ("-c", SETUP)), sudo=False, environment=None)
    cleanup = render_remote_command(
        CommandSpec("bash", ("-c", CLEANUP)), sudo=False, environment=None
    )
    try:
        created = backend.run(
            root, setup, timeout=30, stdin=password.encode() + b"\n", cancel_event=None
        )
        assert 0 == created.exit_code, created.stderr.decode(errors="replace")
        connection = SSHConnection(host, 22, TEST_USER, known_hosts)
        audit = _Audit()
        executor = RemoteExecutor(
            _Resolver(SSHConnectionProfile(connection, password=password)),
            audit,
            backend=backend,
        )
        identity = executor.run("password-sudo", CommandSpec("id", ("-un",)))
        privileged = executor.run("password-sudo", CommandSpec("id", ("-u",)), sudo=True)
        assert TEST_USER == identity.stdout.decode().strip()
        assert "0" == privileged.stdout.decode().strip()
        assert 2 == len(audit.events)
        assert all(password not in event.command_summary for event in audit.events)
    finally:
        removed = backend.run(root, cleanup, timeout=30, stdin=None, cancel_event=None)
        assert 0 == removed.exit_code, removed.stderr.decode(errors="replace")
