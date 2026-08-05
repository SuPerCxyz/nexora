import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from integration.test_remote_kvm import (
    _initialize,
    _onboard,
    _wait_for_task_types,
)
from nexora.app import create_app
from nexora.config import Settings
from nexora.networking.service import NetworkTopologyService

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="remote KVM network topology integration environment is not configured",
)


def test_remote_discovery_builds_management_network_topology(
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
        topology = NetworkTopologyService(client.app.state.database).get(host_id)

    assert topology is not None
    assert any(node.node_type == "physical" for node in topology.nodes)
    assert any(node.node_type == "bridge" for node in topology.nodes)
    assert any(node.node_type == "vnet" for node in topology.nodes)
    assert any(node.management for node in topology.nodes)
    assert any(node.default_route for node in topology.nodes)
    known = {node.id for node in topology.nodes}
    assert all(edge.source in known and edge.target in known for edge in topology.edges)
    assert all(edge.source != edge.target for edge in topology.edges)
