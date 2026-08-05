"""Database-backed redacted command audit sink."""

from datetime import UTC, datetime

from nexora.audit.models import RemoteCommandLog
from nexora.db import Database
from nexora.remote.executor import RemoteCommandAudit


class DatabaseAuditSink:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record(self, event: RemoteCommandAudit) -> None:
        with self.database.session() as session:
            session.add(
                RemoteCommandLog(
                    operation_id=event.operation_id,
                    host_id=event.host_id,
                    command_summary=event.command_summary,
                    exit_code=event.exit_code,
                    timed_out=event.timed_out,
                    cancelled=event.cancelled,
                    stdout_summary=event.stdout_summary,
                    stderr_summary=event.stderr_summary,
                    occurred_at=datetime.now(UTC),
                )
            )
