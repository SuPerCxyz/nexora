import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from integration.test_remote_kvm import _initialize, _onboard, _wait_for_task_types
from nexora.app import create_app
from nexora.config import Settings

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="dedicated remote KVM integration environment is not configured",
)


def test_real_host_hardware_features_and_adapter_mac(settings: Settings) -> None:
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )

        response = client.get(f"/internal/hosts/{host_id}")

    assert 200 == response.status_code
    payload = response.json()
    hardware = payload["hardware"]
    assert hardware["manufacturer"]
    assert hardware["model"]
    assert hardware["architecture"] == "x86_64"
    assert hardware["cpu_model"]
    assert hardware["logical_cpus"] > 0
    assert hardware["memory_bytes"] > 0
    assert any(item["mac"] for item in payload["network_adapters"])
    features = {item["key"]: item["status"] for item in payload["features"]}
    assert "supported" == features["virtualization"]
    assert "supported" == features["network_discovery"]
