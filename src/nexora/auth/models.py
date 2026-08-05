"""Authentication persistence models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class Administrator(Base):
    """The single local Nexora administrator."""

    __tablename__ = "administrators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    session_timeout_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    global_monospace: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    density: Mapped[str] = mapped_column(String(16), nullable=False, default="comfortable")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-CN")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AdminSession(Base):
    """A revocable opaque browser session."""

    __tablename__ = "admin_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    administrator_id: Mapped[int] = mapped_column(
        ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False
    )
    session_version: Mapped[int] = mapped_column(Integer, nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_admin_sessions_expires_at", "expires_at"),)


class LoginAttempt(Base):
    """A bounded record used for login history and throttling."""

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_address: Mapped[str] = mapped_column(String(64), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_login_attempts_occurred_at", "occurred_at"),
        Index("ix_login_attempts_identity", "username", "remote_address", "occurred_at"),
    )
