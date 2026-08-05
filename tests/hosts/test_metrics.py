from datetime import UTC, datetime

import pytest
from vms.test_disk_changes import _runtime

from nexora.hosts.metrics import HostMetrics, HostMetricsError, HostMetricsService
from nexora.hosts.metrics_history import HostMetricsHistoryStore
from nexora.remote.executor import CommandResult


class MetricsExecutor:
    def __init__(self, outputs: list[bytes]) -> None:
        self.outputs = outputs

    def run(self, *_args, **_kwargs) -> CommandResult:
        return CommandResult(
            "operation", 0, self.outputs.pop(0), b"", False, False, False, False, 0.01
        )


def test_host_metrics_service_parses_fixed_procfs_reads(settings) -> None:
    database, _service, _state, _vm_base, _volume_base = _runtime(settings)
    service = HostMetricsService(
        database,
        MetricsExecutor(
            [
                b"0.10 0.20 0.30 1/100 123\n",
                b"MemTotal: 1024 kB\nMemAvailable: 512 kB\n",
                b"123.45 10.00\n",
            ]
        ),  # type: ignore[arg-type]
    )

    metrics = service.sample("host-1")

    assert (0.1, 0.2, 0.3) == (metrics.load_1, metrics.load_5, metrics.load_15)
    assert (1024, 512, 123) == (
        metrics.memory_total_kib,
        metrics.memory_available_kib,
        metrics.uptime_seconds,
    )
    database.dispose()


def test_host_metrics_rejects_incomplete_memory(settings) -> None:
    database, _service, _state, _vm_base, _volume_base = _runtime(settings)
    service = HostMetricsService(
        database,
        MetricsExecutor([b"0 0 0 1/1 1\n", b"MemTotal: 1024 kB\n"]),  # type: ignore[arg-type]
    )

    with pytest.raises(HostMetricsError, match="incomplete"):
        service.sample("host-1")
    database.dispose()


def test_host_metrics_history_is_bounded(settings) -> None:
    database, _service, _state, _vm_base, _volume_base = _runtime(settings)
    store = HostMetricsHistoryStore(database)
    store.MAX_SAMPLES = 2
    metrics = HostMetrics(0.1, 0.2, 0.3, 1024, 512, 123, datetime.now(UTC))

    store.record("host-1", metrics)
    store.record("host-1", metrics)
    store.record("host-1", metrics)

    assert 2 == len(store.query("host-1"))
    database.dispose()
