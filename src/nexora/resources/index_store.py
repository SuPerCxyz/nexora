"""Atomic scan generations and node-scoped resource index updates."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from nexora.db import Database
from nexora.hosts.models import Host
from nexora.resources.contracts import ResourceObservation
from nexora.resources.models import (
    ResourceDocument,
    ResourceIndex,
    ResourceScan,
    ResourceStatus,
    ResourceType,
    ScanStatus,
)


@dataclass(frozen=True)
class SnapshotResult:
    scan_id: str
    generation: int
    resources: tuple[ResourceIndex, ...]


class ResourceIndexStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def begin_scan(self, host_id: str, resource_type: ResourceType) -> ResourceScan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            if session.get(Host, host_id) is None:
                raise ValueError("host not found")
            previous = session.scalar(
                select(func.max(ResourceScan.generation)).where(
                    ResourceScan.host_id == host_id,
                    ResourceScan.resource_type == resource_type,
                )
            )
            scan = ResourceScan(
                id=str(uuid4()),
                host_id=host_id,
                resource_type=resource_type,
                generation=(previous or 0) + 1,
                status=ScanStatus.RUNNING,
                started_at=now,
            )
            session.add(scan)
            session.flush()
            return scan

    def complete_scan(
        self,
        scan_id: str,
        observations: list[ResourceObservation],
        *,
        authoritative_parent_ids: set[str] | None = None,
    ) -> SnapshotResult:
        identities = [item.native_id for item in observations]
        if len(identities) != len(set(identities)):
            raise ValueError("resource snapshot contains duplicate identities")
        now = datetime.now(UTC)
        with self.database.session() as session:
            scan = session.get(ResourceScan, scan_id)
            if scan is None or scan.status != ScanStatus.RUNNING:
                raise ValueError("resource scan is not running")
            existing = {
                item.native_id: item
                for item in session.scalars(
                    select(ResourceIndex).where(
                        ResourceIndex.host_id == scan.host_id,
                        ResourceIndex.resource_type == scan.resource_type,
                    )
                )
            }
            observed: list[ResourceIndex] = []
            for observation in observations:
                item = existing.pop(observation.native_id, None)
                if item is None:
                    item = self._new_index(scan, observation, now)
                    session.add(item)
                    session.flush()
                else:
                    self._update_index(item, scan, observation, now)
                self._replace_documents(session, item, observation, now)
                observed.append(item)
            for missing in existing.values():
                if (
                    authoritative_parent_ids is not None
                    and missing.parent_native_id not in authoritative_parent_ids
                ):
                    continue
                missing.status = ResourceStatus.MISSING
                missing.observed_generation = scan.generation
                missing.missing_since = missing.missing_since or now
            scan.status = ScanStatus.SUCCEEDED
            scan.completed_at = now
            host = session.get(Host, scan.host_id)
            if host is not None:
                host.last_scanned_at = now
                host.updated_at = now
            session.flush()
            return SnapshotResult(scan.id, scan.generation, tuple(observed))

    def apply_snapshot(
        self,
        host_id: str,
        resource_type: ResourceType,
        observations: list[ResourceObservation],
    ) -> SnapshotResult:
        scan = self.begin_scan(host_id, resource_type)
        try:
            return self.complete_scan(scan.id, observations)
        except Exception as exc:
            self.fail_scan(scan.id, str(exc))
            raise

    def fail_scan(self, scan_id: str, error_message: str) -> None:
        with self.database.session() as session:
            scan = session.get(ResourceScan, scan_id)
            if scan is None or scan.status != ScanStatus.RUNNING:
                return
            scan.status = ScanStatus.FAILED
            scan.completed_at = datetime.now(UTC)
            scan.error_message = error_message[:2_048]

    def refresh_one(
        self,
        host_id: str,
        resource_type: ResourceType,
        observation: ResourceObservation,
    ) -> ResourceIndex:
        """Refresh one authoritative resource without declaring peers missing."""

        now = datetime.now(UTC)
        with self.database.session() as session:
            item = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.host_id == host_id,
                    ResourceIndex.resource_type == resource_type,
                    ResourceIndex.native_id == observation.native_id,
                )
            )
            if item is None:
                raise ValueError("resource is not indexed")
            self._apply_observation(item, observation, now)
            self._replace_documents(session, item, observation, now)
            session.flush()
            return item

    def accept_expected_change(
        self,
        resource_id: str,
        *,
        expected_before_hash: str,
        expected_after_hash: str,
        observation: ResourceObservation,
    ) -> ResourceIndex:
        """Persist a verified platform write without flagging it as out-of-band."""

        now = datetime.now(UTC)
        with self.database.session() as session:
            item = session.get(ResourceIndex, resource_id)
            if item is None:
                raise ValueError("resource is not indexed")
            if item.persistent_hash != expected_before_hash:
                raise ValueError("indexed resource changed during VM write")
            if observation.persistent_hash != expected_after_hash:
                raise ValueError("authoritative VM XML does not match proposed XML")
            self._apply_observation(item, observation, now, expected_change=True)
            self._replace_documents(session, item, observation, now)
            session.flush()
            return item

    def _new_index(
        self,
        scan: ResourceScan,
        observation: ResourceObservation,
        now: datetime,
    ) -> ResourceIndex:
        return ResourceIndex(
            id=str(uuid4()),
            host_id=scan.host_id,
            resource_type=scan.resource_type,
            native_id=observation.native_id,
            parent_native_id=observation.parent_native_id,
            display_name=observation.display_name,
            status=observation.status,
            source=observation.source,
            persistent_hash=observation.persistent_hash,
            live_hash=observation.live_hash,
            hash_algorithm=observation.hash_algorithm,
            observed_generation=scan.generation,
            details_json=_details_json(observation),
            labels_json="[]",
            first_seen_at=now,
            last_seen_at=now,
        )

    def _update_index(
        self,
        item: ResourceIndex,
        scan: ResourceScan,
        observation: ResourceObservation,
        now: datetime,
    ) -> None:
        item.observed_generation = scan.generation
        self._apply_observation(item, observation, now)

    def _apply_observation(
        self,
        item: ResourceIndex,
        observation: ResourceObservation,
        now: datetime,
        *,
        expected_change: bool = False,
    ) -> None:
        changed = (
            item.persistent_hash is not None
            and observation.persistent_hash is not None
            and item.persistent_hash != observation.persistent_hash
        )
        preserve_conflict = not expected_change and item.status in {
            ResourceStatus.CHANGED_OUT_OF_BAND,
            ResourceStatus.CONFLICT,
        }
        item.parent_native_id = observation.parent_native_id
        item.display_name = observation.display_name
        item.status = (
            ResourceStatus.CHANGED_OUT_OF_BAND
            if (changed and not expected_change) or preserve_conflict
            else observation.status
        )
        item.source = observation.source
        item.persistent_hash = observation.persistent_hash
        item.live_hash = observation.live_hash
        item.hash_algorithm = observation.hash_algorithm
        item.details_json = _details_json(observation)
        item.last_seen_at = now
        item.missing_since = None

    def _replace_documents(
        self,
        session: Session,
        item: ResourceIndex,
        observation: ResourceObservation,
        now: datetime,
    ) -> None:
        session.execute(
            delete(ResourceDocument).where(
                ResourceDocument.resource_index_id == item.id,
                ResourceDocument.document_kind.not_in(observation.documents),
            )
        )
        stored = {
            document.document_kind: document
            for document in session.scalars(
                select(ResourceDocument).where(ResourceDocument.resource_index_id == item.id)
            )
        }
        algorithm = "sha256-bytes-v1"
        for kind, content in observation.documents.items():
            digest = sha256(content).hexdigest()
            document = stored.get(kind)
            if document is None:
                session.add(
                    ResourceDocument(
                        resource_index_id=item.id,
                        document_kind=kind,
                        content=content,
                        content_hash=digest,
                        hash_algorithm=algorithm,
                        observed_at=now,
                    )
                )
            else:
                document.content = content
                document.content_hash = digest
                document.hash_algorithm = algorithm
                document.observed_at = now


def _details_json(observation: ResourceObservation) -> str:
    return json.dumps(
        observation.details,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
