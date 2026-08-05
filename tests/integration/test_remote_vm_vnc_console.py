import asyncio
import os
from pathlib import Path

import pytest
import websockets
from fastapi.testclient import TestClient
from websockets.typing import Subprotocol

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
    reason="remote KVM VNC integration environment is not configured",
)


def test_remote_vnc_banner_through_ssh_and_websockify(settings: Settings) -> None:
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
        asyncio.run(_read_banner(client, host_id, vm.native_id))
        assert not client.app.state.vnc_proxy_manager.processes


async def _read_banner(client: TestClient, host_id: str, vm_uuid: str) -> None:
    manager = client.app.state.vnc_proxy_manager
    async with (
        manager.open(host_id, vm_uuid) as proxy,
        websockets.connect(
            proxy.websocket_uri,
            subprotocols=[Subprotocol("binary")],
            compression=None,
        ) as websocket,
    ):
        banner = await asyncio.wait_for(websocket.recv(), timeout=5)
        assert isinstance(banner, bytes)
        assert banner.startswith(b"RFB ")
