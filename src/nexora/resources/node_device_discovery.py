"""Read-only discovery of libvirt PCI and USB node devices."""

from dataclasses import dataclass

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.index_store import ResourceIndexStore, SnapshotResult
from nexora.resources.models import ResourceType
from nexora.resources.node_device_parser import parse_node_device

MAX_NODE_DEVICES = 100_000


@dataclass(frozen=True)
class NodeDeviceDiscoveryResult:
    pci: SnapshotResult
    usb: SnapshotResult


class NodeDeviceDiscoveryError(RuntimeError):
    pass


class NodeDeviceDiscoveryService:
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        store: ResourceIndexStore | None = None,
    ) -> None:
        self.database = database
        self.executor = executor
        self.store = store or ResourceIndexStore(database)

    def run(self, host_id: str) -> NodeDeviceDiscoveryResult:
        host = self._host(host_id)
        sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        pci = self._scan_type(host_id, host.libvirt_uri, sudo, ResourceType.PCI_DEVICE)
        usb = self._scan_type(host_id, host.libvirt_uri, sudo, ResourceType.USB_DEVICE)
        return NodeDeviceDiscoveryResult(pci, usb)

    def _scan_type(
        self,
        host_id: str,
        uri: str,
        sudo: bool,
        resource_type: ResourceType,
    ) -> SnapshotResult:
        scan = self.store.begin_scan(host_id, resource_type)
        try:
            capability = "pci" if resource_type == ResourceType.PCI_DEVICE else "usb_device"
            output = self._command(
                host_id,
                ("-c", uri, "nodedev-list", "--cap", capability),
                sudo,
                "node-device enumeration",
            )
            names = [line.strip() for line in output.decode().splitlines() if line.strip()]
            if len(names) > MAX_NODE_DEVICES:
                raise NodeDeviceDiscoveryError("node-device count exceeds safety limit")
            if any(len(name) > 512 or "\0" in name for name in names):
                raise NodeDeviceDiscoveryError("libvirt returned an invalid node-device name")
            if len(names) != len(set(names)):
                raise NodeDeviceDiscoveryError("libvirt returned duplicate node devices")
            observations = [
                parse_node_device(
                    self._command(
                        host_id,
                        ("-c", uri, "nodedev-dumpxml", name),
                        sudo,
                        "node-device XML",
                    ),
                    resource_type,
                )
                for name in names
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
        raise NodeDeviceDiscoveryError(f"{label} failed or returned incomplete output")
