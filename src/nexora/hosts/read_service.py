"""Bounded local reads for managed-host pages."""

from dataclasses import dataclass

from sqlalchemy import func, select

from nexora.db import Database
from nexora.hosts.models import Host, HostCapability, HostFingerprint
from nexora.resources.models import ResourceIndex, ResourceType


@dataclass(frozen=True)
class HostDetail:
    host: Host
    fingerprints: list[HostFingerprint]
    capabilities: list[HostCapability]
    virtual_machines: list[ResourceIndex]
    network_interfaces: list[ResourceIndex]
    pci_devices: list[ResourceIndex]
    resource_counts: dict[str, int]


class HostReadService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_hosts(self, *, limit: int = 500, offset: int = 0) -> list[Host]:
        if not 1 <= limit <= 500:
            raise ValueError("invalid host result limit")
        if offset < 0:
            raise ValueError("invalid host result offset")
        with self.database.session() as session:
            return list(
                session.scalars(select(Host).order_by(Host.name).offset(offset).limit(limit))
            )

    def count_hosts(self) -> int:
        with self.database.session() as session:
            return session.scalar(select(func.count()).select_from(Host)) or 0

    def detail(self, host_id: str) -> HostDetail | None:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                return None
            fingerprints = list(
                session.scalars(
                    select(HostFingerprint)
                    .where(HostFingerprint.host_id == host_id)
                    .order_by(HostFingerprint.id)
                )
            )
            capabilities = list(
                session.scalars(
                    select(HostCapability)
                    .where(HostCapability.host_id == host_id)
                    .order_by(HostCapability.capability_key)
                )
            )
            virtual_machines = list(
                session.scalars(
                    select(ResourceIndex)
                    .where(
                        ResourceIndex.host_id == host_id,
                        ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    )
                    .order_by(ResourceIndex.display_name)
                )
            )
            network_interfaces = list(
                session.scalars(
                    select(ResourceIndex)
                    .where(
                        ResourceIndex.host_id == host_id,
                        ResourceIndex.resource_type == ResourceType.HOST_INTERFACE,
                        ResourceIndex.status != "missing",
                    )
                    .order_by(ResourceIndex.display_name)
                )
            )
            pci_devices = list(
                session.scalars(
                    select(ResourceIndex)
                    .where(
                        ResourceIndex.host_id == host_id,
                        ResourceIndex.resource_type == ResourceType.PCI_DEVICE,
                        ResourceIndex.status != "missing",
                    )
                    .order_by(ResourceIndex.native_id)
                )
            )
            resource_counts = {
                resource_type: count
                for resource_type, count in session.execute(
                    select(ResourceIndex.resource_type, func.count())
                    .where(
                        ResourceIndex.host_id == host_id,
                        ResourceIndex.status != "missing",
                    )
                    .group_by(ResourceIndex.resource_type)
                )
            }
            return HostDetail(
                host,
                fingerprints,
                capabilities,
                virtual_machines,
                network_interfaces,
                pci_devices,
                resource_counts,
            )
