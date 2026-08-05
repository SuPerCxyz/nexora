"""Real encrypted private-key SSH compatibility test."""

import os
from pathlib import Path

import asyncssh
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
TEST_USER = "nexora-it-key"
TEST_HOME = f"/home/{TEST_USER}"
SETUP = f"""set -Eeuo pipefail
getent passwd {TEST_USER} >/dev/null && exit 73
test ! -e {TEST_HOME} || exit 74
trap 'userdel --force --remove {TEST_USER} 2>/dev/null || true; rm -rf {TEST_HOME}' ERR
useradd --home-dir {TEST_HOME} --create-home --shell /bin/bash {TEST_USER}
install -d -m 0700 -o {TEST_USER} -g {TEST_USER} {TEST_HOME}/.ssh
install -m 0600 -o {TEST_USER} -g {TEST_USER} /dev/stdin {TEST_HOME}/.ssh/authorized_keys
trap - ERR
"""
CLEANUP = f"""set -eu
pkill -u {TEST_USER} 2>/dev/null || true
userdel --force --remove {TEST_USER} 2>/dev/null || true
rm -rf {TEST_HOME}
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


def test_real_encrypted_private_key_and_passphrase(tmp_path: Path) -> None:
    host = HOST or ""
    known_hosts = HostKeyStore(tmp_path / "hostkeys").save(
        "key-passphrase", scan_host_keys(host, 22)
    )
    root = SSHConnectionProfile(
        SSHConnection(host, 22, "root", known_hosts),
        private_key=Path(KEY_FILE or "").read_text(),
    )
    backend = AsyncSSHBackend()
    key = asyncssh.generate_private_key("ssh-ed25519")
    passphrase = "nexora-" + os.urandom(18).hex()
    private_key = key.export_private_key("openssh", passphrase=passphrase).decode()
    public_key = key.export_public_key("openssh")
    setup = render_remote_command(CommandSpec("bash", ("-c", SETUP)), sudo=False, environment=None)
    cleanup = render_remote_command(
        CommandSpec("bash", ("-c", CLEANUP)), sudo=False, environment=None
    )
    try:
        created = backend.run(root, setup, timeout=30, stdin=public_key, cancel_event=None)
        assert 0 == created.exit_code, created.stderr.decode(errors="replace")
        audit = _Audit()
        profile = SSHConnectionProfile(
            SSHConnection(host, 22, TEST_USER, known_hosts),
            private_key=private_key,
            private_key_passphrase=passphrase,
        )
        result = RemoteExecutor(_Resolver(profile), audit, backend=backend).run(
            "key-passphrase", CommandSpec("id", ("-un",))
        )
        assert TEST_USER == result.stdout.decode().strip()
        assert 1 == len(audit.events)
        assert passphrase not in audit.events[0].command_summary
    finally:
        removed = backend.run(root, cleanup, timeout=30, stdin=None, cancel_event=None)
        assert 0 == removed.exit_code, removed.stderr.decode(errors="replace")
