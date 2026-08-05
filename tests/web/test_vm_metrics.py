from fastapi.testclient import TestClient
from web.test_vms import DOMAIN_UUID, _initialize, _seed_vm

from nexora.app import create_app
from nexora.config import Settings
from nexora.vms.metrics_history import MetricsHistoryStore


def test_vm_detail_returns_sampled_metrics(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        MetricsHistoryStore(client.app.state.database).record(
            "host-1",
            DOMAIN_UUID,
            state="running",
            cpu_time_ns=None,
            cpu_usage_percent=12.5,
            memory_usage_kib=80_000,
            disk_read_bytes=100,
            disk_write_bytes=50,
            net_rx_bytes=25,
            net_tx_bytes=10,
        )

        response = client.get(f"/internal/hosts/host-1/vms/{DOMAIN_UUID}")

        assert response.status_code == 200
        payload = response.json()
        latest = payload["metrics"][-1]
        assert 12.5 == latest["cpu_usage_percent"]
        assert 80_000 == latest["memory_usage_kib"]
        assert 100 == latest["disk_read_bytes"]
        assert 50 == latest["disk_write_bytes"]
        assert 25 == latest["net_rx_bytes"]
        assert 10 == latest["net_tx_bytes"]
