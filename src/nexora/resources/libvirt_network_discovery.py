"""Read-only discovery of existing libvirt virtual networks."""

from uuid import UUID

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.index_store import ResourceIndexStore, SnapshotResult
from nexora.resources.libvirt_network_parser import (
    parse_network_info,
    parse_network_observation,
)
from nexora.resources.models import ResourceType

MAX_NETWORKS = 10_000


class LibvirtNetworkDiscoveryError(RuntimeError):
    pass


class LibvirtNetworkDiscoveryService:
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
        scan = self.store.begin_scan(host_id, ResourceType.LIBVIRT_NETWORK)
        try:
            network_ids = self._network_uuids(host_id, host.libvirt_uri, sudo)
            observations = [
                parse_network_observation(
                    network_uuid,
                    self._command(
                        host_id,
                        ("-c", host.libvirt_uri, "net-dumpxml", network_uuid),
                        sudo,
                        "libvirt network XML",
                    ),
                    parse_network_info(
                        self._command(
                            host_id,
                            ("-c", host.libvirt_uri, "net-info", network_uuid),
                            sudo,
                            "libvirt network information",
                        )
                    ),
                )
                for network_uuid in network_ids
            ]
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

    def _network_uuids(self, host_id: str, uri: str, sudo: bool) -> list[str]:
        output = self._command(
            host_id,
            ("-c", uri, "net-list", "--all", "--uuid"),
            sudo,
            "libvirt network enumeration",
        )
        try:
            values = [
                str(UUID(line.strip())) for line in output.decode().splitlines() if line.strip()
            ]
        except ValueError as exc:
            raise LibvirtNetworkDiscoveryError("libvirt returned an invalid network UUID") from exc
        if len(values) > MAX_NETWORKS:
            raise LibvirtNetworkDiscoveryError("network count exceeds safety limit")
        if len(values) != len(set(values)):
            raise LibvirtNetworkDiscoveryError("libvirt returned duplicate network UUIDs")
        return values

    def _command(
        self,
        host_id: str,
        arguments: tuple[str, ...],
        sudo: bool,
        label: str,
    ) -> bytes:
        result = self.executor.run(
            host_id,
            CommandSpec("virsh", arguments),
            sudo=sudo,
            timeout=30,
            env={"LC_ALL": "C"},
        )
        _require_success(result, label)
        return result.stdout


def _require_success(result: CommandResult, label: str) -> None:
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    ):
        raise LibvirtNetworkDiscoveryError(f"{label} failed or returned incomplete output")
