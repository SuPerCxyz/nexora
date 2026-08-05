"""Persistence for the latest authoritative host capability scan."""

import json
from datetime import UTC, datetime

from sqlalchemy import select

from nexora.db import Database
from nexora.hosts.capabilities import HostProbeReport
from nexora.hosts.models import Host, HostCapability, HostStatus


class HostCapabilityStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def replace(self, report: HostProbeReport) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            host = session.get(Host, report.host_id)
            if host is None:
                raise LookupError("host does not exist")
            existing = {
                item.capability_key: item
                for item in session.scalars(
                    select(HostCapability).where(HostCapability.host_id == report.host_id)
                )
            }
            observed_keys: set[str] = set()
            for observation in report.observations:
                observed_keys.add(observation.key)
                item = existing.get(observation.key)
                if item is None:
                    item = HostCapability(
                        host_id=report.host_id,
                        capability_key=observation.key,
                        status=observation.status,
                        observed_at=now,
                    )
                    session.add(item)
                item.status = observation.status
                item.value_json = (
                    json.dumps(observation.value, separators=(",", ":"))
                    if observation.value is not None
                    else None
                )
                item.detail = observation.detail
                item.observed_at = now
            for key, stale in existing.items():
                if key not in observed_keys:
                    session.delete(stale)
            host.status = HostStatus.READY if report.healthy else HostStatus.DEGRADED
            host.last_scanned_at = now
            host.updated_at = now
            host.last_error = None

    def mark_failed(self, host_id: str) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is not None:
                host.status = HostStatus.INACCESSIBLE
                host.last_error = "Capability probe failed"
                host.updated_at = now
