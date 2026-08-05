"""Read-only discovery of host interfaces, Bridge, VLAN, addresses, and routes."""

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.host_network_parser import parse_host_interfaces
from nexora.resources.index_store import ResourceIndexStore, SnapshotResult
from nexora.resources.models import ResourceType


class HostNetworkDiscoveryError(RuntimeError):
    pass


class HostNetworkDiscoveryService:
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        store: ResourceIndexStore | None = None,
    ) -> None:
        self.database = database
        self.executor = executor
        self.store = store or ResourceIndexStore(database)

    def run(self, host_id: str) -> SnapshotResult:
        host = self._host(host_id)
        sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        scan = self.store.begin_scan(host_id, ResourceType.HOST_INTERFACE)
        try:
            links = self._required(
                host_id,
                "ip",
                ("-d", "-j", "link", "show"),
                sudo,
                "links",
            )
            addresses = self._required(host_id, "ip", ("-j", "address", "show"), sudo, "addresses")
            routes = self._required(
                host_id,
                "ip",
                ("-j", "route", "show", "table", "all"),
                sudo,
                "routes",
            )
            bridge_links = self._optional(host_id, "bridge", ("-j", "link", "show"), sudo)
            bridge_vlans = self._optional(host_id, "bridge", ("-j", "vlan", "show"), sudo)
            observations = parse_host_interfaces(
                links,
                addresses,
                routes,
                bridge_links,
                bridge_vlans,
            )
            return self.store.complete_scan(scan.id, observations)
        except Exception as exc:
            self.store.fail_scan(scan.id, str(exc))
            raise

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise ValueError("host not found")
            return host

    def _required(
        self,
        host_id: str,
        program: str,
        arguments: tuple[str, ...],
        sudo: bool,
        label: str,
    ) -> bytes:
        result = self._run(host_id, program, arguments, sudo)
        if not _successful(result):
            raise HostNetworkDiscoveryError(
                f"host network {label} failed or returned incomplete output"
            )
        return result.stdout

    def _optional(
        self,
        host_id: str,
        program: str,
        arguments: tuple[str, ...],
        sudo: bool,
    ) -> bytes | None:
        result = self._run(host_id, program, arguments, sudo)
        return result.stdout if _successful(result) else None

    def _run(
        self,
        host_id: str,
        program: str,
        arguments: tuple[str, ...],
        sudo: bool,
    ) -> CommandResult:
        return self.executor.run(
            host_id,
            CommandSpec(program, arguments),
            sudo=sudo,
            timeout=30,
            env={"LC_ALL": "C"},
        )


def _successful(result: CommandResult) -> bool:
    return (
        result.exit_code == 0
        and not result.timed_out
        and not result.cancelled
        and not result.stdout_truncated
        and not result.stderr_truncated
    )
