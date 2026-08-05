"""Persistent console session state without plaintext access tokens."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class ConsoleKind(StrEnum):
    SERIAL = "serial"
    VNC = "vnc"


class ConsoleStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"
    INTERRUPTED = "interrupted"


class ConsoleSession(Base):
    __tablename__ = "console_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    administrator_session_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    vm_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_console_sessions_status_expires", "status", "expires_at"),
        Index("ix_console_sessions_host_vm", "host_id", "vm_uuid"),
    )
