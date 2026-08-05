"""Persistent storage pool change confirmation plans."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class StoragePoolPlanStatus(StrEnum):
    PREVIEW = "preview"
    CONFIRMED = "confirmed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class StoragePoolChangePlan(Base):
    __tablename__ = "storage_pool_change_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host_id: Mapped[str] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    pool_resource_id: Mapped[str | None] = mapped_column(String(36))
    pool_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    pool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    pool_type: Mapped[str] = mapped_column(String(16), nullable=False)
    base_generation: Mapped[int | None] = mapped_column(Integer)
    base_persistent_hash: Mapped[str | None] = mapped_column(String(64))
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    current_xml: Mapped[bytes | None] = mapped_column(LargeBinary)
    proposed_xml: Mapped[bytes | None] = mapped_column(LargeBinary)
    proposed_hash: Mapped[str | None] = mapped_column(String(64))
    diff_text: Mapped[str] = mapped_column(Text, nullable=False)
    confirmation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
