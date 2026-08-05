"""Persistent host-removal plans and immutable audit tombstones."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class HostRemovalMode(StrEnum):
    LOCAL_ONLY = "local_only"
    CLEAN_TEMPORARY = "clean_temporary"


class HostRemovalPlanStatus(StrEnum):
    PREVIEW = "preview"
    CONFIRMED = "confirmed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class HostRemovalPlan(Base):
    __tablename__ = "host_removal_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    host_name: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    original_host_status: Mapped[str] = mapped_column(String(32), nullable=False)
    remote_paths_json: Mapped[str] = mapped_column(Text, nullable=False)
    remote_units_json: Mapped[str] = mapped_column(Text, nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False)
    confirmation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class HostRemovalTombstone(Base):
    __tablename__ = "host_removal_tombstones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_host_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    host_name: Mapped[str] = mapped_column(String(128), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    ssh_port: Mapped[int] = mapped_column(nullable=False)
    fingerprints_json: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    cleanup_summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    removed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
