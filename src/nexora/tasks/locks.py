"""Database-backed resource locks for dangerous write operations."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, delete, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db import Database
from nexora.db.base import Base


class ResourceLock(Base):
    __tablename__ = "resource_locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(512), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "uq_resource_locks_identity",
            "host_id",
            "resource_type",
            "resource_id",
            unique=True,
        ),
        Index("ix_resource_locks_expiry", "expires_at"),
    )


class ResourceLockConflict(RuntimeError):
    pass


class ResourceLockStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def acquire(
        self,
        host_id: str,
        resource_type: str,
        resource_id: str,
        task_id: str,
        *,
        lease_seconds: int = 300,
    ) -> None:
        if not 30 <= lease_seconds <= 3_600:
            raise ValueError("invalid resource lock lease")
        now = datetime.now(UTC)
        try:
            with self.database.session() as session:
                session.execute(delete(ResourceLock).where(ResourceLock.expires_at < now))
                session.add(
                    ResourceLock(
                        host_id=host_id,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        task_id=task_id,
                        acquired_at=now,
                        expires_at=now + timedelta(seconds=lease_seconds),
                    )
                )
                session.flush()
        except IntegrityError:
            raise ResourceLockConflict("resource already has an active write task") from None

    def release(
        self,
        host_id: str,
        resource_type: str,
        resource_id: str,
        task_id: str,
    ) -> None:
        with self.database.session() as session:
            session.execute(
                delete(ResourceLock).where(
                    ResourceLock.host_id == host_id,
                    ResourceLock.resource_type == resource_type,
                    ResourceLock.resource_id == resource_id,
                    ResourceLock.task_id == task_id,
                )
            )

    def renew_task(self, task_id: str, *, lease_seconds: int = 300) -> int:
        """Renew live resource locks owned by one running task."""

        if not 30 <= lease_seconds <= 3_600:
            raise ValueError("invalid resource lock lease")
        now = datetime.now(UTC)
        with self.database.session() as session:
            result = session.execute(
                update(ResourceLock)
                .where(
                    ResourceLock.task_id == task_id,
                    ResourceLock.expires_at >= now,
                )
                .values(expires_at=now + timedelta(seconds=lease_seconds))
            )
            return cast(CursorResult[Any], result).rowcount
