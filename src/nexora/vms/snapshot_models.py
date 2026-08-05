"""Persistent confirmation plans for VM Snapshot operations."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class SnapshotChangePlan(Base):
    __tablename__ = "snapshot_change_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host_id: Mapped[str] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    vm_resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    vm_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    snapshot_name: Mapped[str] = mapped_column(String(128), nullable=False)
    vm_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    vm_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_resource_id: Mapped[str | None] = mapped_column(String(36))
    snapshot_generation: Mapped[int | None] = mapped_column(Integer)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    diff_text: Mapped[str] = mapped_column(Text, nullable=False)
    confirmation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
