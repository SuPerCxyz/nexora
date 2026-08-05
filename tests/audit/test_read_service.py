from datetime import UTC, datetime

import pytest

from nexora.audit.models import RemoteCommandLog
from nexora.audit.read_service import AuditReadService
from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database


def test_audit_read_service_filters_outcomes_and_bounds_summaries(
    settings: Settings,
) -> None:
    database = Database(settings)
    upgrade_database(database)
    _add(database, "success", 0, stdout="x" * 3_000)
    _add(database, "failure", 2, stderr="failed")
    service = AuditReadService(database)

    succeeded = service.page(outcome="succeeded")
    failed = service.page(outcome="failed")

    assert 1 == succeeded.total
    assert "success" == succeeded.items[0].operation_id
    assert 2_048 == len(succeeded.items[0].stdout_summary)
    assert "succeeded" == succeeded.items[0].outcome
    assert 1 == failed.total
    assert "failed" == failed.items[0].outcome
    assert "已移除节点" == failed.items[0].host_name
    with pytest.raises(ValueError, match="filter"):
        service.page(outcome="unknown")
    database.dispose()


def _add(
    database: Database,
    operation_id: str,
    exit_code: int,
    *,
    stdout: str = "",
    stderr: str = "",
) -> None:
    with database.session() as session:
        session.add(
            RemoteCommandLog(
                operation_id=operation_id,
                host_id="removed-host",
                command_summary="virsh list --all",
                exit_code=exit_code,
                timed_out=False,
                cancelled=False,
                stdout_summary=stdout,
                stderr_summary=stderr,
                occurred_at=datetime.now(UTC),
            )
        )
