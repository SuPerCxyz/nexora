"""Bounded persistent VM XML history snapshots for configuration rollback."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import RowMapping, text

from nexora.db import Database

MAX_HISTORY_PER_VM = 10


@dataclass(frozen=True)
class VmXmlSnapshot:
    id: str
    host_id: str
    vm_uuid: str
    xml: str
    xml_hash: str
    created_at: datetime


class VmXmlHistoryStore:
    """Snapshot the persistent XML before each configuration save.

    Only stores the most recent MAX_HISTORY_PER_VM snapshots per VM; older
    entries are removed once a newer snapshot is recorded.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    def record(self, host_id: str, vm_uuid: str, xml: str) -> VmXmlSnapshot | None:
        if not xml.strip():
            return None
        snapshot = VmXmlSnapshot(
            id=str(uuid4()),
            host_id=host_id,
            vm_uuid=vm_uuid,
            xml=xml,
            xml_hash=hashlib.sha256(xml.encode("utf-8")).hexdigest(),
            created_at=datetime.now(UTC),
        )
        with self.database.session() as session:
            existing = session.execute(
                text(
                    "SELECT xml_hash FROM vm_xml_history "
                    "WHERE host_id = :host_id AND vm_uuid = :vm_uuid "
                    "ORDER BY created_at DESC, id DESC LIMIT 1"
                ),
                {"host_id": host_id, "vm_uuid": vm_uuid},
            ).first()
            if existing is not None and existing[0] == snapshot.xml_hash:
                return None
            session.execute(
                text(
                    "INSERT INTO vm_xml_history "
                    "(id, host_id, vm_uuid, xml, xml_hash, created_at) "
                    "VALUES (:id, :host_id, :vm_uuid, :xml, :xml_hash, :created_at)"
                ),
                {
                    "id": snapshot.id,
                    "host_id": snapshot.host_id,
                    "vm_uuid": snapshot.vm_uuid,
                    "xml": snapshot.xml,
                    "xml_hash": snapshot.xml_hash,
                    "created_at": snapshot.created_at,
                },
            )
            session.execute(
                text(
                    "DELETE FROM vm_xml_history WHERE id IN ("
                    "SELECT id FROM ("
                    "SELECT id FROM vm_xml_history "
                    "WHERE host_id = :host_id AND vm_uuid = :vm_uuid "
                    "ORDER BY created_at DESC, id DESC "
                    "LIMIT -1 OFFSET :limit"
                    ") AS stale"
                    ")"
                ),
                {"host_id": host_id, "vm_uuid": vm_uuid, "limit": MAX_HISTORY_PER_VM},
            )
        return snapshot

    def list(self, host_id: str, vm_uuid: str) -> list[VmXmlSnapshot]:
        with self.database.session() as session:
            rows = session.execute(
                text(
                    "SELECT id, host_id, vm_uuid, xml, xml_hash, created_at "
                    "FROM vm_xml_history "
                    "WHERE host_id = :host_id AND vm_uuid = :vm_uuid "
                    "ORDER BY created_at DESC, id DESC LIMIT :limit"
                ),
                {"host_id": host_id, "vm_uuid": vm_uuid, "limit": MAX_HISTORY_PER_VM},
            ).mappings()
            return [_snapshot(row) for row in rows]

    def get(self, snapshot_id: str) -> VmXmlSnapshot | None:
        with self.database.session() as session:
            row = (
                session.execute(
                    text(
                        "SELECT id, host_id, vm_uuid, xml, xml_hash, created_at "
                        "FROM vm_xml_history WHERE id = :id"
                    ),
                    {"id": snapshot_id},
                )
                .mappings()
                .first()
            )
            return _snapshot(row) if row is not None else None

    def clear(self, host_id: str, vm_uuid: str) -> None:
        with self.database.session() as session:
            session.execute(
                text("DELETE FROM vm_xml_history WHERE host_id = :host_id AND vm_uuid = :vm_uuid"),
                {"host_id": host_id, "vm_uuid": vm_uuid},
            )


def _snapshot(row: RowMapping) -> VmXmlSnapshot:
    created_at = row["created_at"]
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
    return VmXmlSnapshot(
        id=row["id"],
        host_id=row["host_id"],
        vm_uuid=row["vm_uuid"],
        xml=row["xml"],
        xml_hash=row["xml_hash"],
        created_at=created_at,
    )
