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
    reason="remote KVM guest-agent integration environment is not configured",
)
VM_NAME = "nexora-it-guest-agent"
VM_UUID = "bcc8e922-3f45-42b2-96f4-d45f25b913ba"
VM_XML = f"""\
<domain type='kvm'>
  <name>{VM_NAME}</name>
  <uuid>{VM_UUID}</uuid>
  <memory unit='MiB'>128</memory>
  <vcpu>1</vcpu>
  <os><type arch='x86_64'>hvm</type></os>
  <devices>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>
  </devices>
</domain>
""".encode()


def test_remote_guest_agent_channel_and_unavailable_state(settings: Settings) -> None:
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
                CommandSpec("virsh", ("-c", "qemu:///system", "define", "/dev/stdin")),
                stdin=VM_XML,
            )
            client.app.state.domain_discovery_service.run(host_id)
            stopped = client.app.state.vm_guest_agent_service.read(host_id, VM_UUID)
            assert "stopped" == stopped.state
            assert stopped.channel_configured

            _remote(
                client,
                host_id,
                CommandSpec("virsh", ("-c", "qemu:///system", "start", VM_UUID)),
            )
            client.app.state.domain_discovery_service.run(host_id)
            unavailable = client.app.state.vm_guest_agent_service.read(host_id, VM_UUID)
            assert "unavailable" == unavailable.state
            assert unavailable.channel_configured
        finally:
            _cleanup(client, host_id)


def _remote(
    client: TestClient,
    host_id: str,
    command: CommandSpec,
    *,
    stdin: bytes | None = None,
    check: bool = True,
) -> None:
    result = client.app.state.remote_executor.run(
        host_id,
        command,
        sudo=False,
        timeout=30,
        stdin=stdin,
        sensitive=stdin is not None,
    )
    if check:
        assert 0 == result.exit_code, result.stderr.decode(errors="replace")


def _cleanup(client: TestClient, host_id: str) -> None:
    for action in (
        ("destroy", VM_UUID),
        ("undefine", VM_UUID, "--nvram"),
        ("undefine", VM_UUID),
    ):
        _remote(
            client,
            host_id,
            CommandSpec("virsh", ("-c", "qemu:///system", *action)),
            check=False,
        )
