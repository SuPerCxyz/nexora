"""Bounded node-scoped VM index reads for server-rendered pages."""

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from nexora.db import Database
from nexora.hosts.models import Host
from nexora.resources.models import ResourceDocument, ResourceIndex, ResourceType


@dataclass(frozen=True)
class VmListItem:
    resource: ResourceIndex
    host_name: str
    details: dict[str, object]


@dataclass(frozen=True)
class VmDetail:
    resource: ResourceIndex
    host: Host
    details: dict[str, object]
    documents: dict[str, str]
    host_device_resources: list[ResourceIndex]


@dataclass(frozen=True)
class VmSnapshotView:
    resource: ResourceIndex
    details: dict[str, object]
    snapshot_xml: str | None


class VmReadService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_vms(
        self,
        *,
        limit: int = 1_000,
        offset: int = 0,
        state: str | None = None,
        host_id: str | None = None,
    ) -> list[VmListItem]:
        if not 1 <= limit <= 5_000:
            raise ValueError("invalid VM result limit")
        if offset < 0:
            raise ValueError("invalid VM result offset")
        statement = self._vm_statement(host_id=host_id)
        with self.database.session() as session:
            rows = list(session.execute(statement))
        items = [
            VmListItem(resource, host_name, _details(resource.details_json))
            for resource, host_name in rows
        ]
        if state is not None:
            items = [item for item in items if str(item.details.get("state", "")) == state]
        return items[offset : offset + limit]

    def count_vms(self, *, state: str | None = None, host_id: str | None = None) -> int:
        if state is None and host_id is None:
            statement = (
                select(func.count())
                .select_from(ResourceIndex)
                .where(ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE)
            )
            with self.database.session() as session:
                return session.scalar(statement) or 0
        return len(self.list_vms(limit=5_000, state=state, host_id=host_id))

    @staticmethod
    def _vm_statement(*, host_id: str | None = None) -> Select[tuple[ResourceIndex, str]]:
        conditions = [ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE]
        if host_id is not None:
            conditions.append(ResourceIndex.host_id == host_id)
        return (
            select(ResourceIndex, Host.name)
            .join(Host, Host.id == ResourceIndex.host_id)
            .where(*conditions)
            .order_by(ResourceIndex.display_name, Host.name)
        )

    def detail(self, host_id: str, domain_uuid: str) -> VmDetail | None:
        canonical_uuid = str(UUID(domain_uuid))
        with self.database.session() as session:
            resource = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                    ResourceIndex.native_id == canonical_uuid,
                )
            )
            host = session.get(Host, host_id)
            if resource is None or host is None:
                return None
            documents = {
                item.document_kind: item.content.decode("utf-8", errors="replace")
                for item in session.scalars(
                    select(ResourceDocument).where(
                        ResourceDocument.resource_index_id == resource.id
                    )
                )
            }
            host_device_resources = list(
                session.scalars(
                    select(ResourceIndex)
                    .where(
                        ResourceIndex.host_id == host_id,
                        ResourceIndex.resource_type.in_(
                            (ResourceType.PCI_DEVICE, ResourceType.USB_DEVICE)
                        ),
                        ResourceIndex.status != "missing",
                    )
                    .order_by(ResourceIndex.resource_type, ResourceIndex.native_id)
                    .limit(5_000)
                )
            )
            return VmDetail(
                resource,
                host,
                _details(resource.details_json),
                documents,
                host_device_resources,
            )

    def snapshots(
        self,
        host_id: str,
        domain_uuid: str,
        *,
        limit: int = 2_000,
    ) -> list[VmSnapshotView]:
        canonical_uuid = str(UUID(domain_uuid))
        if not 1 <= limit <= 2_000:
            raise ValueError("invalid snapshot result limit")
        statement = (
            select(ResourceIndex)
            .where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == ResourceType.SNAPSHOT,
                ResourceIndex.parent_native_id == canonical_uuid,
            )
            .order_by(ResourceIndex.display_name, ResourceIndex.id)
            .limit(limit)
        )
        with self.database.session() as session:
            resources = list(session.scalars(statement))
            documents = _documents_by_resource(session, resources, "snapshot_xml")
            return [
                VmSnapshotView(
                    resource,
                    _details(resource.details_json),
                    documents.get(resource.id),
                )
                for resource in resources
            ]


def _details(content: str) -> dict[str, object]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("stored VM details are invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("stored VM details are invalid")
    return value


def _documents_by_resource(
    session: Session,
    resources: list[ResourceIndex],
    document_kind: str,
) -> dict[str, str]:
    if not resources:
        return {}
    identifiers = [resource.id for resource in resources]
    statement = select(ResourceDocument).where(
        ResourceDocument.resource_index_id.in_(identifiers),
        ResourceDocument.document_kind == document_kind,
    )
    values = session.scalars(statement)
    return {
        item.resource_index_id: item.content.decode("utf-8", errors="replace") for item in values
    }
