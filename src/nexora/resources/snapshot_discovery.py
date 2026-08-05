"""Read-only discovery of existing libvirt domain snapshots."""

from uuid import UUID

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.contracts import ResourceObservation
from nexora.resources.index_store import ResourceIndexStore, SnapshotResult
from nexora.resources.models import ResourceType
from nexora.resources.snapshot_parser import parse_snapshot_observation

MAX_SNAPSHOTS = 100_000


class SnapshotDiscoveryError(RuntimeError):
    pass


class SnapshotDiscoveryService:
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
        scan = self.store.begin_scan(host_id, ResourceType.SNAPSHOT)
        try:
            domains = self._domain_uuids(host_id, host.libvirt_uri, sudo)
            observations: list[ResourceObservation] = []
            for domain_uuid in domains:
                observations.extend(
                    self._domain_snapshots(
                        host_id,
                        host.libvirt_uri,
                        domain_uuid,
                        sudo,
                    )
                )
                if len(observations) > MAX_SNAPSHOTS:
                    raise SnapshotDiscoveryError("snapshot count exceeds safety limit")
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

    def _domain_uuids(self, host_id: str, uri: str, sudo: bool) -> list[str]:
        output = self._command(
            host_id,
            ("-c", uri, "list", "--all", "--uuid"),
            sudo,
            "domain enumeration",
        )
        try:
            return [
                str(UUID(line.strip())) for line in output.decode().splitlines() if line.strip()
            ]
        except ValueError as exc:
            raise SnapshotDiscoveryError("libvirt returned an invalid domain UUID") from exc

    def _domain_snapshots(
        self,
        host_id: str,
        uri: str,
        domain_uuid: str,
        sudo: bool,
    ) -> list[ResourceObservation]:
        output = self._command(
            host_id,
            ("-c", uri, "snapshot-list", domain_uuid, "--name"),
            sudo,
            "snapshot enumeration",
        )
        names = [line.strip() for line in output.decode().splitlines() if line.strip()]
        if len(names) != len(set(names)):
            raise SnapshotDiscoveryError("libvirt returned duplicate snapshot names")
        if any(len(name) > 255 or "\0" in name for name in names):
            raise SnapshotDiscoveryError("libvirt returned an invalid snapshot name")
        current = self._current_snapshot(host_id, uri, domain_uuid, sudo, names)
        return [
            parse_snapshot_observation(
                domain_uuid,
                name,
                self._command(
                    host_id,
                    ("-c", uri, "snapshot-dumpxml", domain_uuid, name),
                    sudo,
                    "snapshot XML",
                ),
                current=name == current,
            )
            for name in names
        ]

    def _current_snapshot(
        self,
        host_id: str,
        uri: str,
        domain_uuid: str,
        sudo: bool,
        names: list[str],
    ) -> str | None:
        if not names:
            return None
        output = self._command(
            host_id,
            ("-c", uri, "snapshot-current", domain_uuid, "--name"),
            sudo,
            "current snapshot",
        )
        current = output.decode().strip()
        if current not in names:
            raise SnapshotDiscoveryError("libvirt returned an unknown current snapshot")
        return current

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
        raise SnapshotDiscoveryError(f"{label} failed or returned incomplete output")
