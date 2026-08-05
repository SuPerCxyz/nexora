"""Bounded real-time VM metrics sampling over virsh domstats."""

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from time import monotonic_ns

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor

MAX_LINES = 4_096
MAX_DEVICES = 1_024
MAX_CACHE_ENTRIES = 2_000
CACHE_TTL_NS = 15 * 60 * 1_000_000_000
STATE_NAMES = {
    0: "unknown",
    1: "running",
    2: "blocked",
    3: "paused",
    4: "shutting_down",
    5: "shut_off",
    6: "crashed",
    7: "suspended",
}


class VmMetricsError(RuntimeError):
    pass


@dataclass(frozen=True)
class VmCounters:
    cpu_ns: int
    block_read_bytes: int
    block_write_bytes: int
    network_rx_bytes: int
    network_tx_bytes: int


@dataclass(frozen=True)
class VmMetrics:
    state: str
    memory_current_kib: int | None
    memory_maximum_kib: int | None
    memory_rss_kib: int | None
    cpu_percent: float | None
    block_read_bps: float | None
    block_write_bps: float | None
    network_rx_bps: float | None
    network_tx_bps: float | None
    sampled_at: datetime
    cpu_time_ns: int = 0
    block_read_bytes: int = 0
    block_write_bytes: int = 0
    network_rx_bytes: int = 0
    network_tx_bytes: int = 0


@dataclass(frozen=True)
class _Sample:
    monotonic_ns: int
    counters: VmCounters


class VmMetricsService:
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        *,
        clock: Callable[[], int] = monotonic_ns,
    ) -> None:
        self.database = database
        self.executor = executor
        self.clock = clock
        self._samples: OrderedDict[tuple[str, str], _Sample] = OrderedDict()
        self._lock = Lock()

    def sample(self, host_id: str, vm_uuid: str) -> VmMetrics:
        host = self._host(host_id)
        try:
            result = self.executor.run(
                host_id,
                CommandSpec(
                    "virsh",
                    (
                        "-c",
                        host.libvirt_uri,
                        "domstats",
                        vm_uuid,
                        "--state",
                        "--cpu-total",
                        "--balloon",
                        "--block",
                        "--interface",
                    ),
                ),
                sudo=host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS,
                timeout=15,
                env={"LC_ALL": "C"},
            )
        except Exception as exc:
            raise VmMetricsError("libvirt metrics query failed") from exc
        values = parse_domstats(_complete_output(result))
        now_ns = self.clock()
        counters = _counters(values)
        previous = self._remember((host_id, vm_uuid), _Sample(now_ns, counters))
        rates = _rates(previous, _Sample(now_ns, counters))
        return VmMetrics(
            state=STATE_NAMES.get(_integer(values, "state.state", 0), "unknown"),
            memory_current_kib=_optional_integer(values, "balloon.current"),
            memory_maximum_kib=_optional_integer(values, "balloon.maximum"),
            memory_rss_kib=_optional_integer(values, "balloon.rss"),
            cpu_percent=rates[0],
            block_read_bps=rates[1],
            block_write_bps=rates[2],
            network_rx_bps=rates[3],
            network_tx_bps=rates[4],
            sampled_at=datetime.now(UTC),
            cpu_time_ns=counters.cpu_ns,
            block_read_bytes=counters.block_read_bytes,
            block_write_bytes=counters.block_write_bytes,
            network_rx_bytes=counters.network_rx_bytes,
            network_tx_bytes=counters.network_tx_bytes,
        )

    def _remember(self, key: tuple[str, str], sample: _Sample) -> _Sample | None:
        with self._lock:
            expired_before = sample.monotonic_ns - CACHE_TTL_NS
            expired = [
                item_key
                for item_key, item in self._samples.items()
                if item.monotonic_ns < expired_before
            ]
            for item_key in expired:
                self._samples.pop(item_key, None)
            previous = self._samples.pop(key, None)
            self._samples[key] = sample
            while len(self._samples) > MAX_CACHE_ENTRIES:
                self._samples.popitem(last=False)
            return previous

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise VmMetricsError("host not found")
            return host


def parse_domstats(content: bytes) -> dict[str, str]:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise VmMetricsError("libvirt metrics output is not UTF-8") from exc
    if len(lines) > MAX_LINES:
        raise VmMetricsError("libvirt metrics output exceeds the line limit")
    values: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("Domain:"):
            continue
        if "=" not in line:
            raise VmMetricsError("libvirt metrics output is malformed")
        key, value = line.split("=", 1)
        if not key or len(key) > 128 or len(value) > 256:
            raise VmMetricsError("libvirt metrics field exceeds the size limit")
        values[key] = value
    if "state.state" not in values:
        raise VmMetricsError("libvirt metrics state is missing")
    return values


def _counters(values: dict[str, str]) -> VmCounters:
    block_count = _integer(values, "block.count", 0)
    network_count = _integer(values, "net.count", 0)
    if block_count > MAX_DEVICES or network_count > MAX_DEVICES:
        raise VmMetricsError("libvirt metrics device count exceeds the limit")
    return VmCounters(
        cpu_ns=_integer(values, "cpu.time", 0),
        block_read_bytes=sum(
            _integer(values, f"block.{index}.rd.bytes", 0) for index in range(block_count)
        ),
        block_write_bytes=sum(
            _integer(values, f"block.{index}.wr.bytes", 0) for index in range(block_count)
        ),
        network_rx_bytes=sum(
            _integer(values, f"net.{index}.rx.bytes", 0) for index in range(network_count)
        ),
        network_tx_bytes=sum(
            _integer(values, f"net.{index}.tx.bytes", 0) for index in range(network_count)
        ),
    )


def _rates(
    previous: _Sample | None,
    current: _Sample,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    if previous is None or current.monotonic_ns <= previous.monotonic_ns:
        return (None, None, None, None, None)
    old = previous.counters
    new = current.counters
    counters = (
        new.cpu_ns - old.cpu_ns,
        new.block_read_bytes - old.block_read_bytes,
        new.block_write_bytes - old.block_write_bytes,
        new.network_rx_bytes - old.network_rx_bytes,
        new.network_tx_bytes - old.network_tx_bytes,
    )
    if any(value < 0 for value in counters):
        return (None, None, None, None, None)
    elapsed_ns = current.monotonic_ns - previous.monotonic_ns
    factor = 1_000_000_000 / elapsed_ns
    return (
        counters[0] / elapsed_ns * 100,
        counters[1] * factor,
        counters[2] * factor,
        counters[3] * factor,
        counters[4] * factor,
    )


def _integer(values: dict[str, str], key: str, default: int) -> int:
    value = values.get(key)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise VmMetricsError(f"libvirt metrics field {key} is invalid") from exc
    if parsed < 0:
        raise VmMetricsError(f"libvirt metrics field {key} is negative")
    return parsed


def _optional_integer(values: dict[str, str], key: str) -> int | None:
    return _integer(values, key, 0) if key in values else None


def _complete_output(result: CommandResult) -> bytes:
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    ):
        raise VmMetricsError("libvirt metrics query failed or returned incomplete output")
    return result.stdout
