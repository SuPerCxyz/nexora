import pytest

from nexora.remote.executor import CommandResult
from nexora.vms.metrics import VmMetricsError, VmMetricsService, _counters, parse_domstats
from vms.test_disk_changes import _runtime


class MetricsExecutor:
    def __init__(self, outputs: list[bytes]) -> None:
        self.outputs = outputs

    def run(self, *_args, **_kwargs) -> CommandResult:
        return CommandResult(
            "operation",
            0,
            self.outputs.pop(0),
            b"",
            False,
            False,
            False,
            False,
            0.01,
        )


class FailingExecutor:
    def run(self, *_args, **_kwargs) -> CommandResult:
        raise RuntimeError("SSH transport unavailable")


def test_metrics_service_aggregates_rates_without_sqlite_history(settings) -> None:
    database, _disk_service, _state, vm_base, _volume_base = _runtime(settings)
    first = _output(cpu=1_000_000_000, read=100, write=20, rx=50, tx=10)
    second = _output(cpu=2_000_000_000, read=300, write=70, rx=80, tx=50)
    ticks = iter((1_000_000_000, 2_000_000_000))
    service = VmMetricsService(
        database,
        MetricsExecutor([first, second]),  # type: ignore[arg-type]
        clock=lambda: next(ticks),
    )

    initial = service.sample("host-1", vm_base.native_id)
    current = service.sample("host-1", vm_base.native_id)

    assert initial.cpu_percent is None
    assert current.cpu_percent == 100.0
    assert current.block_read_bps == 200.0
    assert current.block_write_bps == 50.0
    assert current.network_rx_bps == 30.0
    assert current.network_tx_bps == 40.0
    assert current.memory_current_kib == 524_288
    database.dispose()


def test_domstats_parser_rejects_malformed_or_unbounded_values() -> None:
    with pytest.raises(VmMetricsError, match="malformed"):
        parse_domstats(b"state.state=1\nnot-a-field\n")
    with pytest.raises(VmMetricsError, match="device count"):
        values = parse_domstats(b"state.state=1\nblock.count=1025\n")
        _counters(values)


def test_metrics_service_wraps_remote_execution_failure(settings) -> None:
    database, _disk_service, _state, vm_base, _volume_base = _runtime(settings)
    service = VmMetricsService(database, FailingExecutor())  # type: ignore[arg-type]

    with pytest.raises(VmMetricsError, match="query failed"):
        service.sample("host-1", vm_base.native_id)
    database.dispose()


def _output(*, cpu: int, read: int, write: int, rx: int, tx: int) -> bytes:
    return (
        "Domain: 'vm'\n"
        "  state.state=1\n"
        f"  cpu.time={cpu}\n"
        "  balloon.current=524288\n"
        "  balloon.maximum=524288\n"
        "  balloon.rss=80000\n"
        "  block.count=1\n"
        f"  block.0.rd.bytes={read}\n"
        f"  block.0.wr.bytes={write}\n"
        "  net.count=1\n"
        f"  net.0.rx.bytes={rx}\n"
        f"  net.0.tx.bytes={tx}\n"
    ).encode()
