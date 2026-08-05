import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from integration.test_remote_kvm import (
    _initialize,
    _onboard,
    _resource,
    _wait_for_task_types,
)
from nexora.app import create_app
from nexora.config import Settings
from nexora.resources.models import ResourceType

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="remote KVM serial-console integration environment is not configured",
)


def test_remote_serial_console_opens_and_closes_without_remote_change(
    settings: Settings,
) -> None:
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        vm = _resource(
            client,
            host_id,
            ResourceType.VIRTUAL_MACHINE,
            "nexora-it-existing",
        )
        asyncio.run(_open_and_close(client, host_id, vm.native_id))


async def _open_and_close(client: TestClient, host_id: str, vm_uuid: str) -> None:
    connector = client.app.state.serial_console_connector
    async with connector.open(host_id, vm_uuid) as connection:
        assert connection.process.exit_status is None
        connection.write(b"\r")
        await asyncio.sleep(0.2)
