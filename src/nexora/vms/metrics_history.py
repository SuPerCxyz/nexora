"""Low-frequency VM metrics history model and store."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from nexora.db import Database
from nexora.vms.metrics import VmMetrics


class MetricsHistoryStore:
    """Persist and query bounded VM metrics history."""

    MAX_SAMPLES = 240  # 24h at 6-minute intervals

    def __init__(self, database: Database) -> None:
        self.database = database

    def record(
        self,
        host_id: str,
        vm_uuid: str,
        *,
        state: str,
        cpu_time_ns: int | None,
        cpu_usage_percent: float | None,
        memory_usage_kib: int | None,
        disk_read_bytes: int | None,
        disk_write_bytes: int | None,
        net_rx_bytes: int | None,
        net_tx_bytes: int | None,
    ) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            _insert_metrics(
                session,
                str(uuid4()),
                host_id,
                vm_uuid,
                now,
                state,
                cpu_time_ns,
                cpu_usage_percent,
                memory_usage_kib,
                disk_read_bytes,
                disk_write_bytes,
                net_rx_bytes,
                net_tx_bytes,
            )
            self._prune(session, host_id, vm_uuid)

    def record_metrics(self, host_id: str, vm_uuid: str, metrics: VmMetrics) -> None:
        self.record(
            host_id,
            vm_uuid,
            state=metrics.state,
            cpu_time_ns=metrics.cpu_time_ns,
            cpu_usage_percent=metrics.cpu_percent,
            memory_usage_kib=metrics.memory_current_kib,
            disk_read_bytes=metrics.block_read_bytes,
            disk_write_bytes=metrics.block_write_bytes,
            net_rx_bytes=metrics.network_rx_bytes,
            net_tx_bytes=metrics.network_tx_bytes,
        )

    def query(
        self,
        host_id: str,
        vm_uuid: str,
        *,
        since: datetime | None = None,
    ) -> list[dict[str, object]]:
        cutoff = since or (datetime.now(UTC) - timedelta(hours=24))
        with self.database.session() as session:
            from sqlalchemy import text

            rows = session.execute(
                text(
                    "SELECT sampled_at, state, cpu_usage_percent, memory_usage_kib, "
                    "disk_read_bytes, disk_write_bytes, net_rx_bytes, net_tx_bytes "
                    "FROM vm_metrics_history "
                    "WHERE host_id = :host_id AND vm_uuid = :vm_uuid "
                    "AND sampled_at >= :cutoff ORDER BY sampled_at"
                ),
                {"host_id": host_id, "vm_uuid": vm_uuid, "cutoff": cutoff},
            )
            return [
                {
                    "sampled_at": row[0],
                    "state": row[1],
                    "cpu_usage_percent": row[2],
                    "memory_usage_kib": row[3],
                    "disk_read_bytes": row[4],
                    "disk_write_bytes": row[5],
                    "net_rx_bytes": row[6],
                    "net_tx_bytes": row[7],
                }
                for row in rows
            ]

    def _prune(self, session: Session, host_id: str, vm_uuid: str) -> None:
        from sqlalchemy import text

        session.execute(
            text(
                "DELETE FROM vm_metrics_history WHERE id IN ("
                "  SELECT id FROM vm_metrics_history "
                "  WHERE host_id = :host_id AND vm_uuid = :vm_uuid "
                "  ORDER BY sampled_at DESC LIMIT -1 OFFSET :limit"
                ")"
            ),
            {"host_id": host_id, "vm_uuid": vm_uuid, "limit": self.MAX_SAMPLES},
        )


def _insert_metrics(
    session: Session,
    sample_id: str,
    host_id: str,
    vm_uuid: str,
    sampled_at: datetime,
    state: str,
    cpu_time_ns: int | None,
    cpu_usage_percent: float | None,
    memory_usage_kib: int | None,
    disk_read_bytes: int | None,
    disk_write_bytes: int | None,
    net_rx_bytes: int | None,
    net_tx_bytes: int | None,
) -> None:
    from sqlalchemy import text

    session.execute(
        text(
            "INSERT INTO vm_metrics_history "
            "(id, host_id, vm_uuid, sampled_at, state, cpu_time_ns, "
            "cpu_usage_percent, memory_usage_kib, disk_read_bytes, "
            "disk_write_bytes, net_rx_bytes, net_tx_bytes) "
            "VALUES (:id, :host_id, :vm_uuid, :sampled_at, :state, :cpu_time_ns, "
            ":cpu_usage_percent, :memory_usage_kib, :disk_read_bytes, "
            ":disk_write_bytes, :net_rx_bytes, :net_tx_bytes)"
        ),
        {
            "id": sample_id,
            "host_id": host_id,
            "vm_uuid": vm_uuid,
            "sampled_at": sampled_at,
            "state": state,
            "cpu_time_ns": cpu_time_ns,
            "cpu_usage_percent": cpu_usage_percent,
            "memory_usage_kib": memory_usage_kib,
            "disk_read_bytes": disk_read_bytes,
            "disk_write_bytes": disk_write_bytes,
            "net_rx_bytes": net_rx_bytes,
            "net_tx_bytes": net_tx_bytes,
        },
    )
