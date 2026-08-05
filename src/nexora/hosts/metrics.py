"""Bounded host performance sampling through fixed procfs reads."""

from dataclasses import dataclass
from datetime import UTC, datetime

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor


class HostMetricsError(RuntimeError):
    pass


@dataclass(frozen=True)
class HostMetrics:
    load_1: float
    load_5: float
    load_15: float
    memory_total_kib: int
    memory_available_kib: int
    uptime_seconds: int
    sampled_at: datetime


class HostMetricsService:
    def __init__(self, database: Database, executor: RemoteExecutor) -> None:
        self.database = database
        self.executor = executor

    def sample(self, host_id: str) -> HostMetrics:
        host = self._host(host_id)
        sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        load_values = _load(_read(self.executor, host_id, "/proc/loadavg", sudo))
        memory_values = _memory(_read(self.executor, host_id, "/proc/meminfo", sudo))
        uptime = _read(self.executor, host_id, "/proc/uptime", sudo)
        return HostMetrics(
            *load_values,
            *memory_values,
            uptime_seconds=_uptime(uptime),
            sampled_at=datetime.now(UTC),
        )

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise HostMetricsError("host not found")
            return host


def _output(result: CommandResult) -> bytes:
    if result.exit_code or result.timed_out or result.cancelled or result.stdout_truncated:
        raise HostMetricsError("host metrics query failed")
    if len(result.stdout) > 64 * 1024:
        raise HostMetricsError("host metrics output exceeds the limit")
    return result.stdout


def _read(executor: RemoteExecutor, host_id: str, path: str, sudo: bool) -> bytes:
    return _output(executor.run(host_id, CommandSpec("cat", (path,)), sudo=sudo, timeout=10))


def _load(content: bytes) -> tuple[float, float, float]:
    fields = _text(content).split()
    if len(fields) < 3:
        raise HostMetricsError("load average output is malformed")
    try:
        values = tuple(float(value) for value in fields[:3])
    except ValueError as exc:
        raise HostMetricsError("load average output is invalid") from exc
    if any(value < 0 for value in values):
        raise HostMetricsError("load average output is negative")
    return values[0], values[1], values[2]


def _memory(content: bytes) -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in _text(content).splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] in {"MemTotal:", "MemAvailable:"}:
            try:
                values[fields[0]] = int(fields[1])
            except ValueError as exc:
                raise HostMetricsError("memory output is invalid") from exc
    if "MemTotal:" not in values or "MemAvailable:" not in values:
        raise HostMetricsError("memory output is incomplete")
    if values["MemTotal:"] <= 0 or not 0 <= values["MemAvailable:"] <= values["MemTotal:"]:
        raise HostMetricsError("memory output is outside valid bounds")
    return values["MemTotal:"], values["MemAvailable:"]


def _uptime(content: bytes) -> int:
    fields = _text(content).split()
    if not fields:
        raise HostMetricsError("uptime output is malformed")
    try:
        value = int(float(fields[0]))
    except ValueError as exc:
        raise HostMetricsError("uptime output is invalid") from exc
    if value < 0:
        raise HostMetricsError("uptime output is negative")
    return value


def _text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HostMetricsError("host metrics output is not UTF-8") from exc
