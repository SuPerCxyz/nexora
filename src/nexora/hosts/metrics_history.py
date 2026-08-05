"""Bounded persistence for low-frequency host metrics."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from nexora.db import Database
from nexora.hosts.metrics import HostMetrics


class HostMetricsHistoryStore:
    MAX_SAMPLES = 240

    def __init__(self, database: Database) -> None:
        self.database = database

    def record(self, host_id: str, metrics: HostMetrics) -> None:
        with self.database.session() as session:
            session.execute(
                text(
                    "INSERT INTO host_metrics_history "
                    "(id, host_id, sampled_at, load_1, load_5, load_15, "
                    "memory_total_kib, memory_available_kib, uptime_seconds) "
                    "VALUES (:id, :host_id, :sampled_at, :load_1, :load_5, :load_15, "
                    ":memory_total_kib, :memory_available_kib, :uptime_seconds)"
                ),
                {"id": str(uuid4()), "host_id": host_id, **metrics.__dict__},
            )
            self._prune(session, host_id)

    def query(self, host_id: str) -> list[dict[str, object]]:
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        with self.database.session() as session:
            rows = session.execute(
                text(
                    "SELECT sampled_at, load_1, load_5, load_15, memory_total_kib, "
                    "memory_available_kib, uptime_seconds FROM host_metrics_history "
                    "WHERE host_id = :host_id AND sampled_at >= :cutoff ORDER BY sampled_at"
                ),
                {"host_id": host_id, "cutoff": cutoff},
            )
            return [dict(row._mapping) for row in rows]

    def _prune(self, session: Session, host_id: str) -> None:
        session.execute(
            text(
                "DELETE FROM host_metrics_history WHERE id IN ("
                "SELECT id FROM host_metrics_history WHERE host_id = :host_id "
                "ORDER BY sampled_at DESC LIMIT -1 OFFSET :limit)"
            ),
            {"host_id": host_id, "limit": self.MAX_SAMPLES},
        )
