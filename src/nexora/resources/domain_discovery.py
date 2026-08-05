"""Read-only discovery of existing libvirt domains over RemoteExecutor."""

from collections.abc import Callable
from dataclasses import replace
from uuid import UUID

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.contracts import ResourceObservation
from nexora.resources.domain_parser import parse_domain_observation
from nexora.resources.index_store import ResourceIndexStore, SnapshotResult
from nexora.resources.models import ResourceType

DiscoveryProgress = Callable[[float, str], None]
MAX_DOMAINS = 5_000


class DomainDiscoveryError(RuntimeError):
    """A complete and trustworthy VM snapshot could not be collected."""


class DomainDiscoveryService:
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        store: ResourceIndexStore | None = None,
    ) -> None:
        self.database = database
        self.executor = executor
        self.store = store or ResourceIndexStore(database)

    def run(
        self,
        host_id: str,
        *,
        progress: DiscoveryProgress | None = None,
    ) -> SnapshotResult:
        host = self._host(host_id)
        use_sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        scan = self.store.begin_scan(host_id, ResourceType.VIRTUAL_MACHINE)
        try:
            self._notify(progress, 2, "Enumerating existing virtual machines")
            uuids = self._list_domains(host_id, host.libvirt_uri, use_sudo)
            observations = [
                self._read_domain(
                    host_id,
                    host.libvirt_uri,
                    domain_uuid,
                    use_sudo,
                    progress,
                    offset,
                    len(uuids),
                )
                for offset, domain_uuid in enumerate(uuids)
            ]
            self._notify(progress, 90, "Persisting authoritative VM snapshot")
            result = self.store.complete_scan(scan.id, observations)
            self._notify(progress, 100, "Virtual machine discovery complete")
            return result
        except Exception as exc:
            self.store.fail_scan(scan.id, str(exc))
            raise

    def read_one(self, host_id: str, domain_uuid: str) -> ResourceObservation:
        """Re-read one VM from the remote authority before or after a write."""

        host = self._host(host_id)
        canonical_uuid = str(UUID(domain_uuid))
        use_sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        return self._read_domain(
            host_id,
            host.libvirt_uri,
            canonical_uuid,
            use_sudo,
            None,
            0,
            1,
        )

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise ValueError("host not found")
            return host

    def _list_domains(self, host_id: str, uri: str, sudo: bool) -> list[str]:
        output = self._command(
            host_id,
            CommandSpec("virsh", ("-c", uri, "list", "--all", "--uuid")),
            sudo=sudo,
            label="domain enumeration",
        )
        values = [line.strip() for line in output.decode().splitlines() if line.strip()]
        if len(values) > MAX_DOMAINS:
            raise DomainDiscoveryError("domain count exceeds safety limit")
        try:
            uuids = [str(UUID(value)) for value in values]
        except ValueError as exc:
            raise DomainDiscoveryError("libvirt returned an invalid domain UUID") from exc
        if len(uuids) != len(set(uuids)):
            raise DomainDiscoveryError("libvirt returned duplicate domain UUIDs")
        return uuids

    def _read_domain(
        self,
        host_id: str,
        uri: str,
        domain_uuid: str,
        sudo: bool,
        progress: DiscoveryProgress | None,
        offset: int,
        total: int,
    ) -> ResourceObservation:
        self._notify(
            progress,
            5 + (offset / max(1, total)) * 80,
            f"Reading VM {offset + 1} of {total}",
        )
        info = _parse_dominfo(
            self._command(
                host_id,
                CommandSpec("virsh", ("-c", uri, "dominfo", domain_uuid)),
                sudo=sudo,
                label="domain information",
            )
        )
        persistent_xml = (
            self._command(
                host_id,
                CommandSpec("virsh", ("-c", uri, "dumpxml", "--inactive", domain_uuid)),
                sudo=sudo,
                label="persistent domain XML",
            )
            if info.persistent
            else None
        )
        live_xml = (
            self._command(
                host_id,
                CommandSpec("virsh", ("-c", uri, "dumpxml", domain_uuid)),
                sudo=sudo,
                label="live domain XML",
            )
            if info.active
            else None
        )
        snapshots = self._snapshot_names(host_id, uri, domain_uuid, sudo)
        observation = parse_domain_observation(
            domain_uuid,
            persistent_xml,
            live_xml,
            state=info.state,
            autostart=info.autostart,
        )
        return replace(
            observation,
            details={
                **observation.details,
                "active": info.active,
                "managed_save": info.managed_save,
                "snapshot_names": snapshots,
            },
        )

    def _snapshot_names(
        self,
        host_id: str,
        uri: str,
        domain_uuid: str,
        sudo: bool,
    ) -> list[str]:
        output = self._command(
            host_id,
            CommandSpec("virsh", ("-c", uri, "snapshot-list", domain_uuid, "--name")),
            sudo=sudo,
            label="domain snapshot enumeration",
        )
        return [line.strip() for line in output.decode().splitlines() if line.strip()]

    def _command(
        self,
        host_id: str,
        command: CommandSpec,
        *,
        sudo: bool,
        label: str,
    ) -> bytes:
        result = self.executor.run(
            host_id,
            command,
            sudo=sudo,
            timeout=30,
            env={"LC_ALL": "C"},
        )
        _require_success(result, label)
        return result.stdout

    def _notify(
        self,
        progress: DiscoveryProgress | None,
        percentage: float,
        message: str,
    ) -> None:
        if progress is not None:
            progress(percentage, message)


class _DomainInfo:
    def __init__(
        self,
        *,
        state: str,
        active: bool,
        persistent: bool,
        autostart: bool,
        managed_save: bool,
    ) -> None:
        self.state = state
        self.active = active
        self.persistent = persistent
        self.autostart = autostart
        self.managed_save = managed_save


def _parse_dominfo(output: bytes) -> _DomainInfo:
    fields: dict[str, str] = {}
    for line in output.decode("utf-8", errors="strict").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip().lower()] = value.strip()
    required = {"id", "state", "persistent", "autostart"}
    if not required <= fields.keys():
        raise DomainDiscoveryError("libvirt domain information is incomplete")
    return _DomainInfo(
        state=fields["state"],
        active=fields["id"] != "-",
        persistent=_enabled(fields["persistent"]),
        autostart=_enabled(fields["autostart"]),
        managed_save=_enabled(fields.get("managed save", "no")),
    )


def _enabled(value: str) -> bool:
    return value.lower() in {"yes", "enable", "enabled", "on", "1"}


def _require_success(result: CommandResult, label: str) -> None:
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    ):
        raise DomainDiscoveryError(f"{label} failed or returned incomplete output")
