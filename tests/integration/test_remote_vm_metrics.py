import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from integration.test_remote_kvm import _initialize, _onboard, _wait_for_task_types
from nexora.app import create_app
from nexora.config import Settings
from nexora.resources.models import ResourceIndex, ResourceType

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="remote KVM metrics integration environment is not configured",
)


def test_remote_vm_domstats_are_sampled_without_persistence(settings: Settings) -> None:
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        with client.app.state.database.session() as session:
            vm = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.display_name == "nexora-it-existing",
                )
            )
            assert vm is not None
            vm_uuid = vm.native_id

        host = client.app.state.metrics_sampler.host_service.sample(host_id)
        first = client.app.state.vm_metrics_service.sample(host_id, vm_uuid)
        time.sleep(0.2)
        second = client.app.state.vm_metrics_service.sample(host_id, vm_uuid)

        assert host.memory_total_kib > 0
        assert 0 <= host.memory_available_kib <= host.memory_total_kib
        assert host.uptime_seconds > 0
        assert min(host.load_1, host.load_5, host.load_15) >= 0
        assert first.state in {"running", "shut_off", "paused"}
        assert first.memory_maximum_kib is not None
        for value in (
            second.cpu_percent,
            second.block_read_bps,
            second.block_write_bps,
            second.network_rx_bps,
            second.network_tx_bps,
        ):
            assert value is not None and value >= 0
