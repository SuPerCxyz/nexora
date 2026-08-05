"""Atomic media scan generations and index persistence."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from nexora.db import Database
from nexora.media.models import (
    MediaItem,
    MediaScan,
    MediaScanStatus,
    MediaStatus,
)


@dataclass(frozen=True)
class MediaObservation:
    relative_path: str
    file_name: str
    kind: str
    size_bytes: int
    modified_ns: int
    file_device: int
    file_inode: int
    sha256: str
    image_format: str | None
    virtual_size_bytes: int | None
    backing_chain: tuple[str, ...]
    classification: str | None
    architecture: str | None


class MediaIndexStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def begin(self) -> MediaScan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            previous = session.scalar(select(func.max(MediaScan.generation)))
            scan = MediaScan(
                id=str(uuid4()),
                generation=(previous or 0) + 1,
                status=MediaScanStatus.RUNNING,
                started_at=now,
            )
            session.add(scan)
            session.flush()
            return scan

    def complete(self, scan_id: str, observations: list[MediaObservation]) -> int:
        paths = [item.relative_path for item in observations]
        if len(paths) != len(set(paths)):
            raise ValueError("media snapshot contains duplicate paths")
        now = datetime.now(UTC)
        with self.database.session() as session:
            scan = session.get(MediaScan, scan_id)
            if scan is None or scan.status != MediaScanStatus.RUNNING:
                raise ValueError("media scan is not running")
            existing = {item.relative_path: item for item in session.scalars(select(MediaItem))}
            for observation in observations:
                item = existing.pop(observation.relative_path, None)
                if item is None:
                    item = _new_item(observation, scan.generation, now)
                    session.add(item)
                else:
                    _update_item(item, observation, scan.generation, now)
            for missing in existing.values():
                missing.status = MediaStatus.MISSING
                missing.observed_generation = scan.generation
                missing.missing_since = missing.missing_since or now
            scan.status = MediaScanStatus.SUCCEEDED
            scan.completed_at = now
            return len(observations)

    def fail(self, scan_id: str, error: str) -> None:
        with self.database.session() as session:
            scan = session.get(MediaScan, scan_id)
            if scan is None or scan.status != MediaScanStatus.RUNNING:
                return
            scan.status = MediaScanStatus.FAILED
            scan.completed_at = datetime.now(UTC)
            scan.error_message = error[:2_048]

    def list_items(self, *, limit: int = 5_000) -> list[MediaItem]:
        if not 1 <= limit <= 10_000:
            raise ValueError("invalid media result limit")
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(MediaItem)
                    .order_by(MediaItem.status, MediaItem.kind, MediaItem.relative_path)
                    .limit(limit)
                )
            )

    def get_item(self, media_item_id: str) -> MediaItem | None:
        with self.database.session() as session:
            return session.get(MediaItem, media_item_id)


def _new_item(
    observation: MediaObservation,
    generation: int,
    now: datetime,
) -> MediaItem:
    return MediaItem(
        id=str(uuid4()),
        relative_path=observation.relative_path,
        file_name=observation.file_name,
        kind=observation.kind,
        status=MediaStatus.AVAILABLE,
        size_bytes=observation.size_bytes,
        modified_ns=observation.modified_ns,
        file_device=observation.file_device,
        file_inode=observation.file_inode,
        sha256=observation.sha256,
        image_format=observation.image_format,
        virtual_size_bytes=observation.virtual_size_bytes,
        backing_chain_json=_json(observation.backing_chain),
        classification=observation.classification,
        architecture=observation.architecture,
        observed_generation=generation,
        first_seen_at=now,
        last_seen_at=now,
    )


def _update_item(
    item: MediaItem,
    observation: MediaObservation,
    generation: int,
    now: datetime,
) -> None:
    item.file_name = observation.file_name
    item.kind = observation.kind
    item.status = MediaStatus.AVAILABLE
    item.size_bytes = observation.size_bytes
    item.modified_ns = observation.modified_ns
    item.file_device = observation.file_device
    item.file_inode = observation.file_inode
    item.sha256 = observation.sha256
    item.image_format = observation.image_format
    item.virtual_size_bytes = observation.virtual_size_bytes
    item.backing_chain_json = _json(observation.backing_chain)
    item.classification = observation.classification
    item.architecture = observation.architecture
    item.observed_generation = generation
    item.last_seen_at = now
    item.missing_since = None


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
