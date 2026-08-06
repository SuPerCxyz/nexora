"""Read-only Linux, libvirt, and initial VM capability probe."""

from collections.abc import Callable
from dataclasses import dataclass

from nexora.db import Database
from nexora.hosts.capabilities import (
    CapabilityObservation,
    CapabilityStatus,
    HostProbeReport,
    JsonValue,
)
from nexora.hosts.capability_store import HostCapabilityStore
from nexora.hosts.models import Host, HostStatus, SudoMode
from nexora.hosts.probe_parsers import parse_lines, parse_lscpu, parse_nodeinfo, parse_os_release
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor

ProbeProgress = Callable[[int, int, str], None]
Parser = Callable[[bytes], JsonValue]


@dataclass(frozen=True)
class ToolProbe:
    name: str
    required: bool = False


TOOLS = (
    ToolProbe("virsh", required=True),
    ToolProbe("virt-install"),
    ToolProbe("virt-xml"),
    ToolProbe("virt-xml-validate"),
    ToolProbe("qemu-img"),
    ToolProbe("ip"),
    ToolProbe("bridge"),
    ToolProbe("nmcli"),
    ToolProbe("networkctl"),
    ToolProbe("netplan"),
    ToolProbe("mount.nfs"),
    ToolProbe("ovs-vsctl"),
)


class HostProbeService:
    """Execute a bounded sequence of standard read-only commands."""

    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        store: HostCapabilityStore | None = None,
    ) -> None:
        self.database = database
        self.executor = executor
        self.store = store or HostCapabilityStore(database)

    def run(
        self,
        host_id: str,
        *,
        progress: ProbeProgress | None = None,
    ) -> HostProbeReport:
        host = self._begin(host_id)
        use_sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        observations: list[CapabilityObservation] = []
        total = 10 + len(TOOLS)
        try:
            observations.append(
                self._run(
                    1, total, host_id, "system.uname", CommandSpec("uname", ("-srm",)), progress
                )
            )
            observations.append(
                self._run(
                    2,
                    total,
                    host_id,
                    "system.os_release",
                    CommandSpec("cat", ("/etc/os-release",)),
                    progress,
                    parser=parse_os_release,
                )
            )
            observations.append(
                self._run(
                    3,
                    total,
                    host_id,
                    "system.lscpu",
                    CommandSpec("lscpu", ("-J",)),
                    progress,
                    parser=parse_lscpu,
                )
            )
            observations.append(
                self._run(
                    4,
                    total,
                    host_id,
                    "system.manufacturer",
                    CommandSpec("cat", ("/sys/class/dmi/id/sys_vendor",)),
                    progress,
                )
            )
            observations.append(
                self._run(
                    5,
                    total,
                    host_id,
                    "system.product_name",
                    CommandSpec("cat", ("/sys/class/dmi/id/product_name",)),
                    progress,
                )
            )
            observations.extend(self._identity(host_id, 6, total, use_sudo, progress))
            for offset, tool in enumerate(TOOLS, start=8):
                observations.append(self._tool(host_id, offset, total, tool, progress))
            observations.extend(
                self._libvirt(
                    host_id,
                    8 + len(TOOLS),
                    total,
                    host.libvirt_uri,
                    use_sudo,
                    progress,
                )
            )
        except Exception:
            self.store.mark_failed(host_id)
            raise
        report = HostProbeReport(host_id, tuple(observations))
        self.store.replace(report)
        return report

    def _begin(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None or host.status not in {HostStatus.READY, HostStatus.DEGRADED}:
                raise ValueError("host is not ready for capability probing")
            host.status = HostStatus.SCANNING
            return host

    def _identity(
        self,
        host_id: str,
        sequence: int,
        total: int,
        use_sudo: bool,
        progress: ProbeProgress | None,
    ) -> list[CapabilityObservation]:
        identity = self._run(
            sequence,
            total,
            host_id,
            "system.identity",
            CommandSpec("id", ("-u",)),
            progress,
        )
        if progress is not None:
            progress(sequence + 1, total, "system.sudo")
        if identity.status != CapabilityStatus.NORMAL:
            sudo = CapabilityObservation(
                "system.sudo",
                CapabilityStatus.UNKNOWN,
                detail="identity check failed",
            )
        elif identity.value == "0":
            sudo = CapabilityObservation("system.sudo", CapabilityStatus.NORMAL, "not_required")
        elif not use_sudo:
            sudo = CapabilityObservation(
                "system.sudo",
                CapabilityStatus.PERMISSION_DENIED,
                detail="passwordless sudo is not configured",
            )
        else:
            sudo = self._result_observation(
                "system.sudo",
                self.executor.run(
                    host_id,
                    CommandSpec("true"),
                    sudo=True,
                    timeout=10,
                    env={"LC_ALL": "C"},
                ),
            )
        return [identity, sudo]

    def _tool(
        self,
        host_id: str,
        sequence: int,
        total: int,
        tool: ToolProbe,
        progress: ProbeProgress | None,
    ) -> CapabilityObservation:
        key = f"tool.{tool.name}"
        if progress is not None:
            progress(sequence, total, key)
        result = self.executor.run(
            host_id,
            CommandSpec("command", ("-v", tool.name)),
            timeout=10,
        )
        if result.exit_code == 0:
            return CapabilityObservation(
                key,
                CapabilityStatus.NORMAL,
                result.stdout.decode(errors="replace").strip(),
            )
        status = (
            CapabilityStatus.REQUIRED_MISSING
            if tool.required
            else CapabilityStatus.OPTIONAL_MISSING
        )
        return CapabilityObservation(key, status)

    def _libvirt(
        self,
        host_id: str,
        start: int,
        total: int,
        uri: str,
        use_sudo: bool,
        progress: ProbeProgress | None,
    ) -> list[CapabilityObservation]:
        return [
            self._run(
                start,
                total,
                host_id,
                "libvirt.version",
                CommandSpec("virsh", ("-c", uri, "version")),
                progress,
                sudo=use_sudo,
            ),
            self._run(
                start + 1,
                total,
                host_id,
                "libvirt.nodeinfo",
                CommandSpec("virsh", ("-c", uri, "nodeinfo")),
                progress,
                sudo=use_sudo,
                parser=parse_nodeinfo,
            ),
            self._run(
                start + 2,
                total,
                host_id,
                "libvirt.domain_uuids",
                CommandSpec("virsh", ("-c", uri, "list", "--all", "--uuid")),
                progress,
                sudo=use_sudo,
                parser=parse_lines,
            ),
        ]

    def _run(
        self,
        sequence: int,
        total: int,
        host_id: str,
        key: str,
        command: CommandSpec,
        progress: ProbeProgress | None,
        *,
        sudo: bool = False,
        parser: Parser | None = None,
    ) -> CapabilityObservation:
        if progress is not None:
            progress(sequence, total, key)
        result = self.executor.run(
            host_id,
            command,
            sudo=sudo,
            timeout=30,
            env={"LC_ALL": "C"},
        )
        return self._result_observation(key, result, parser=parser)

    def _result_observation(
        self,
        key: str,
        result: CommandResult,
        *,
        parser: Parser | None = None,
    ) -> CapabilityObservation:
        if result.timed_out or result.cancelled:
            return CapabilityObservation(
                key,
                CapabilityStatus.UNKNOWN,
                detail="command timed out or was cancelled",
            )
        if result.exit_code != 0:
            detail = result.stderr[:512].decode("utf-8", errors="replace").strip()
            status = (
                CapabilityStatus.PERMISSION_DENIED
                if "permission denied" in detail.lower()
                else CapabilityStatus.UNKNOWN
            )
            return CapabilityObservation(key, status, detail=detail or None)
        if result.stdout_truncated or result.stderr_truncated:
            return CapabilityObservation(
                key,
                CapabilityStatus.UNKNOWN,
                detail="command output exceeded limit",
            )
        value: JsonValue
        if parser is not None:
            value = parser(result.stdout)
        else:
            value = result.stdout.decode("utf-8", errors="replace").strip()
        return CapabilityObservation(key, CapabilityStatus.NORMAL, value)
