"""Database-backed read-only host network topology service."""

from sqlalchemy import select

from nexora.db import Database
from nexora.hosts.models import Host
from nexora.networking.topology import build_network_topology
from nexora.networking.topology_models import NetworkTopology
from nexora.resources.models import ResourceIndex, ResourceType


class NetworkTopologyService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, host_id: str) -> NetworkTopology | None:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                return None
            resources = list(
                session.scalars(
                    select(ResourceIndex)
                    .where(
                        ResourceIndex.host_id == host_id,
                        ResourceIndex.resource_type.in_(
                            (
                                ResourceType.HOST_INTERFACE,
                                ResourceType.VIRTUAL_MACHINE,
                            )
                        ),
                    )
                    .order_by(
                        ResourceIndex.resource_type,
                        ResourceIndex.display_name,
                        ResourceIndex.native_id,
                    )
                )
            )
            session.expunge(host)
            for resource in resources:
                session.expunge(resource)
        return build_network_topology(host, resources)
