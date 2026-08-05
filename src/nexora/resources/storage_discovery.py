"""Read-only discovery of existing libvirt storage pools and volumes."""

from dataclasses import dataclass, replace

from sqlalchemy import select

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.contracts import ResourceObservation
from nexora.resources.index_store import ResourceIndexStore, SnapshotResult
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_parser import (
    WRITABLE_POOL_TYPES,
    PoolInfo,
    parse_pool_info,
    parse_pool_observation,
    parse_volume_list,
    parse_volume_observation,
)

MAX_POOLS = 5_000
MAX_VOLUMES = 100_000


@dataclass(frozen=True)
class StorageDiscoveryResult:
    pools: SnapshotResult
    volumes: SnapshotResult


class StorageDiscoveryError(RuntimeError):
    pass


class StorageDiscoveryService:
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        store: ResourceIndexStore | None = None,
    ) -> None:
        self.database = database
        self.executor = executor
        self.store = store or ResourceIndexStore(database)

    def run(self, host_id: str) -> StorageDiscoveryResult:
        host = self._host(host_id)
        sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        pool_scan = self.store.begin_scan(host_id, ResourceType.STORAGE_POOL)
        try:
            pool_names = self._pool_names(host_id, host.libvirt_uri, sudo)
            pools = [
                self._pool(host_id, host.libvirt_uri, pool_name, sudo) for pool_name in pool_names
            ]
            pool_result = self.store.complete_scan(
                pool_scan.id,
                [observation for observation, _info in pools],
            )
        except Exception as exc:
            self.store.fail_scan(pool_scan.id, str(exc))
            raise

        volume_scan = self.store.begin_scan(host_id, ResourceType.STORAGE_VOLUME)
        try:
            active = {observation.native_id for observation, info in pools if info.active}
            authoritative_parents = active | self._missing_pool_ids(host_id)
            volumes: list[ResourceObservation] = []
            for pool, info in pools:
                if not info.active:
                    continue
                volumes.extend(
                    self._volumes(
                        host_id,
                        host.libvirt_uri,
                        pool,
                        sudo,
                    )
                )
                if len(volumes) > MAX_VOLUMES:
                    raise StorageDiscoveryError("volume count exceeds safety limit")
            volume_result = self.store.complete_scan(
                volume_scan.id,
                volumes,
                authoritative_parent_ids=authoritative_parents if pool_names else None,
            )
        except Exception as exc:
            self.store.fail_scan(volume_scan.id, str(exc))
            raise
        return StorageDiscoveryResult(pool_result, volume_result)

    def read_pool(self, host_id: str, pool_uuid: str) -> ResourceObservation:
        """Read one authoritative pool without changing peer resource state."""

        host = self._host(host_id)
        sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        observation, _info = self._pool(
            host_id,
            host.libvirt_uri,
            pool_uuid,
            sudo,
            expected_uuid=pool_uuid,
        )
        return observation

    def read_volume(
        self,
        host_id: str,
        pool_uuid: str,
        volume: str,
    ) -> ResourceObservation:
        """Read one authoritative volume by name, key, or path."""

        host = self._host(host_id)
        sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        content = self._command(
            host_id,
            ("-c", host.libvirt_uri, "vol-dumpxml", volume, "--pool", pool_uuid),
            sudo,
            "storage volume XML",
        )
        return parse_volume_observation(pool_uuid, content)

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise ValueError("host not found")
            return host

    def _missing_pool_ids(self, host_id: str) -> set[str]:
        with self.database.session() as session:
            return set(
                session.scalars(
                    select(ResourceIndex.native_id).where(
                        ResourceIndex.host_id == host_id,
                        ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                        ResourceIndex.status == ResourceStatus.MISSING,
                    )
                )
            )

    def _pool_names(self, host_id: str, uri: str, sudo: bool) -> list[str]:
        output = self._command(
            host_id,
            ("-c", uri, "pool-list", "--all", "--name"),
            sudo,
            "storage pool enumeration",
        )
        values = [line.strip() for line in output.decode().splitlines() if line.strip()]
        if len(values) > MAX_POOLS:
            raise StorageDiscoveryError("pool count exceeds safety limit")
        if any(len(value) > 255 or "\0" in value for value in values):
            raise StorageDiscoveryError("libvirt returned an invalid pool name")
        if len(values) != len(set(values)):
            raise StorageDiscoveryError("libvirt returned duplicate pool names")
        return values

    def _pool(
        self,
        host_id: str,
        uri: str,
        pool_name: str,
        sudo: bool,
        *,
        expected_uuid: str | None = None,
    ) -> tuple[ResourceObservation, PoolInfo]:
        info = parse_pool_info(
            self._command(
                host_id,
                ("-c", uri, "pool-info", pool_name),
                sudo,
                "storage pool information",
            )
        )
        observation = parse_pool_observation(
            expected_uuid,
            self._command(
                host_id,
                ("-c", uri, "pool-dumpxml", pool_name),
                sudo,
                "storage pool XML",
            ),
            info,
        )
        return observation, info

    def _volumes(
        self,
        host_id: str,
        uri: str,
        pool: ResourceObservation,
        sudo: bool,
    ) -> list[ResourceObservation]:
        output = self._command(
            host_id,
            ("-c", uri, "vol-list", pool.native_id),
            sudo,
            "storage volume enumeration",
        )
        names = parse_volume_list(output)
        writable = pool.details.get("pool_type") in WRITABLE_POOL_TYPES
        return [
            replace(
                parse_volume_observation(
                    pool.native_id,
                    self._command(
                        host_id,
                        ("-c", uri, "vol-dumpxml", name, "--pool", pool.native_id),
                        sudo,
                        "storage volume XML",
                    ),
                ),
                status=ResourceStatus.MANAGED if writable else ResourceStatus.READ_ONLY,
            )
            for name in names
        ]

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
        raise StorageDiscoveryError(f"{label} failed or returned incomplete output")
