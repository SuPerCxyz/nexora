"""Persistent full resource discovery task orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.host_network_discovery import HostNetworkDiscoveryService
from nexora.resources.libvirt_network_discovery import LibvirtNetworkDiscoveryService
from nexora.resources.node_device_discovery import NodeDeviceDiscoveryService
from nexora.resources.snapshot_discovery import SnapshotDiscoveryService
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus

TOTAL_STEPS = 6
ResultT = TypeVar("ResultT")


@dataclass
class FullResourceDiscoveryHandler:
    domains: DomainDiscoveryService
    snapshots: SnapshotDiscoveryService
    storage: StorageDiscoveryService
    networks: LibvirtNetworkDiscoveryService
    host_network: HostNetworkDiscoveryService
    devices: NodeDeviceDiscoveryService

    def __call__(self, context: TaskContext, task: Task) -> str:
        if task.host_id is None:
            raise ValueError("resource discovery task has no host")
        host_id = task.host_id
        summaries: list[str] = []
        domain_result = self._step(
            context,
            1,
            "discover.virtual_machines",
            lambda: self.domains.run(
                host_id,
                progress=lambda percentage, message: context.checkpoint(
                    progress=percentage / TOTAL_STEPS,
                    current_step=1,
                    message=message,
                ),
            ),
        )
        summaries.append(f"vms={len(domain_result.resources)}")
        snapshot_result = self._step(
            context,
            2,
            "discover.snapshots",
            lambda: self.snapshots.run(host_id),
        )
        summaries.append(f"snapshots={len(snapshot_result.resources)}")
        storage_result = self._step(
            context,
            3,
            "discover.storage",
            lambda: self.storage.run(host_id),
        )
        summaries.append(
            f"pools={len(storage_result.pools.resources)},"
            f"volumes={len(storage_result.volumes.resources)}"
        )
        network_result = self._step(
            context,
            4,
            "discover.libvirt_networks",
            lambda: self.networks.run(host_id),
        )
        summaries.append(f"networks={len(network_result.resources)}")
        interface_result = self._step(
            context,
            5,
            "discover.host_network",
            lambda: self.host_network.run(host_id),
        )
        summaries.append(f"interfaces={len(interface_result.resources)}")
        device_result = self._step(
            context,
            6,
            "discover.node_devices",
            lambda: self.devices.run(host_id),
        )
        summaries.append(
            f"pci={len(device_result.pci.resources)},usb={len(device_result.usb.resources)}"
        )
        return "; ".join(summaries)

    def _step(
        self,
        context: TaskContext,
        sequence: int,
        name: str,
        action: Callable[[], ResultT],
    ) -> ResultT:
        context.start_step(sequence, name)
        context.checkpoint(
            progress=(sequence - 1) / TOTAL_STEPS * 100,
            current_step=sequence,
            message=name,
        )
        try:
            result = action()
        except Exception:
            context.finish_step(sequence, TaskStepStatus.FAILED)
            raise
        context.finish_step(sequence)
        context.checkpoint(
            progress=sequence / TOTAL_STEPS * 100,
            current_step=sequence,
            message=f"{name} complete",
        )
        return result
