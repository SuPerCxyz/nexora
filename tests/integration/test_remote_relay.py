import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from integration.test_remote_kvm import _initialize, _onboard, _wait_for_task_types
from nexora.app import create_app
from nexora.config import Settings
from nexora.remote.commands import CommandSpec

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="remote relay integration environment is not configured",
)
SOURCE = "/var/tmp/nexora-relay-integration.source"
TARGET = "/var/tmp/nexora-relay-integration.partial"


def test_remote_relay_same_host_streams_without_local_file(settings: Settings) -> None:
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        _cleanup(client, host_id)
        try:
            _remote(
                client,
                host_id,
                CommandSpec(
                    "dd",
                    ("if=/dev/zero", f"of={SOURCE}", "bs=1048576", "count=2", "status=none"),
                ),
            )
            progress: list[int] = []
            result = client.app.state.remote_relay_transfer.copy(
                host_id,
                host_id,
                CommandSpec("dd", (f"if={SOURCE}", "bs=1048576", "status=none")),
                CommandSpec(
                    "dd",
                    (f"of={TARGET}", "bs=1048576", "conv=fsync", "status=none"),
                ),
                source_sudo=False,
                target_sudo=False,
                timeout=30,
                progress=progress.append,
            )
            assert (0, 0) == (result.source_exit_code, result.target_exit_code)
            assert 2 * 1024 * 1024 == result.bytes_copied
            assert result.bytes_copied == progress[-1]
            hashes = (
                _remote(
                    client,
                    host_id,
                    CommandSpec("sha256sum", (SOURCE, TARGET)),
                )
                .decode()
                .splitlines()
            )
            assert hashes[0].split()[0] == hashes[1].split()[0]
        finally:
            _cleanup(client, host_id)


def _remote(client: TestClient, host_id: str, command: CommandSpec) -> bytes:
    result = client.app.state.remote_executor.run(host_id, command, timeout=30)
    assert 0 == result.exit_code, result.stderr.decode(errors="replace")
    return result.stdout


def _cleanup(client: TestClient, host_id: str) -> None:
    for path in (SOURCE, TARGET):
        client.app.state.remote_executor.run(
            host_id,
            CommandSpec("rm", ("-f", "--", path)),
            timeout=30,
        )
