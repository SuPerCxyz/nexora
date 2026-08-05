"""Bounded read models for redacted remote command audit history."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select

from nexora.audit.models import RemoteCommandLog
from nexora.db import Database
from nexora.hosts.models import Host

PAGE_SIZE = 50
MAX_PAGE = 10_000


@dataclass(frozen=True)
class AuditLogView:
    operation_id: str
    host_id: str
    host_name: str
    command_summary: str
    outcome: str
    exit_code: int
    stdout_summary: str
    stderr_summary: str
    occurred_at: datetime


@dataclass(frozen=True)
class AuditLogPage:
    items: tuple[AuditLogView, ...]
    page: int
    total: int
    has_previous: bool
    has_next: bool


class AuditReadService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def page(
        self,
        *,
        page: int = 1,
        host_id: str | None = None,
        outcome: str = "all",
    ) -> AuditLogPage:
        if not 1 <= page <= MAX_PAGE:
            raise ValueError("audit page is invalid")
        if outcome not in {"all", "succeeded", "failed"}:
            raise ValueError("audit outcome filter is invalid")
        conditions = []
        if host_id:
            conditions.append(RemoteCommandLog.host_id == host_id)
        if outcome == "succeeded":
            conditions.extend(
                (
                    RemoteCommandLog.exit_code == 0,
                    RemoteCommandLog.timed_out.is_(False),
                    RemoteCommandLog.cancelled.is_(False),
                )
            )
        elif outcome == "failed":
            conditions.append(
                (RemoteCommandLog.exit_code != 0)
                | RemoteCommandLog.timed_out.is_(True)
                | RemoteCommandLog.cancelled.is_(True)
            )
        with self.database.session() as session:
            total = (
                session.scalar(
                    select(func.count()).select_from(RemoteCommandLog).where(*conditions)
                )
                or 0
            )
            logs = list(
                session.scalars(
                    select(RemoteCommandLog)
                    .where(*conditions)
                    .order_by(RemoteCommandLog.occurred_at.desc(), RemoteCommandLog.id.desc())
                    .offset((page - 1) * PAGE_SIZE)
                    .limit(PAGE_SIZE)
                )
            )
            names = {host.id: host.name for host in session.scalars(select(Host))}
        items = tuple(_view(item, names.get(item.host_id)) for item in logs)
        return AuditLogPage(
            items,
            page,
            total,
            page > 1,
            page * PAGE_SIZE < total,
        )


def _view(item: RemoteCommandLog, host_name: str | None) -> AuditLogView:
    outcome = (
        "timed_out"
        if item.timed_out
        else "cancelled"
        if item.cancelled
        else "succeeded"
        if item.exit_code == 0
        else "failed"
    )
    return AuditLogView(
        item.operation_id,
        item.host_id,
        host_name or "已移除节点",
        item.command_summary[:2_048],
        outcome,
        item.exit_code,
        item.stdout_summary[:2_048],
        item.stderr_summary[:2_048],
        item.occurred_at,
    )
