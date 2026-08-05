"""Persistent redacted remote command audit records."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class RemoteCommandLog(Base):
    __tablename__ = "remote_command_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    host_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    command_summary: Mapped[str] = mapped_column(Text, nullable=False)
    exit_code: Mapped[int] = mapped_column(Integer, nullable=False)
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stdout_summary: Mapped[str] = mapped_column(Text, nullable=False)
    stderr_summary: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
