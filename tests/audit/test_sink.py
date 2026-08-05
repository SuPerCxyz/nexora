from collections.abc import Iterator

import pytest
from sqlalchemy import select

from nexora.audit.models import RemoteCommandLog
from nexora.audit.sink import DatabaseAuditSink
from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.remote.executor import RemoteCommandAudit


@pytest.fixture
def audit_database(settings: Settings) -> Iterator[Database]:
    database = Database(settings)
    upgrade_database(database)
    try:
        yield database
    finally:
        database.dispose()


def test_redacted_remote_command_audit_is_persistent(audit_database: Database) -> None:
    sink = DatabaseAuditSink(audit_database)
    sink.record(
        RemoteCommandAudit(
            operation_id="operation-1",
            host_id="host-1",
            command_summary="[sensitive command]",
            exit_code=0,
            timed_out=False,
            cancelled=False,
            stdout_summary="",
            stderr_summary="",
        )
    )

    with audit_database.session() as session:
        stored = session.scalar(
            select(RemoteCommandLog).where(RemoteCommandLog.operation_id == "operation-1")
        )
        assert stored is not None
        assert "[sensitive command]" == stored.command_summary
        assert "" == stored.stdout_summary
