"""Persistent storage volume change confirmation plans."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class StorageVolumeChangePlan(Base):
    __tablename__ = "storage_volume_change_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host_id: Mapped[str] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    pool_resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    pool_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    volume_resource_id: Mapped[str | None] = mapped_column(String(36))
    volume_native_id: Mapped[str | None] = mapped_column(String(512))
    volume_name: Mapped[str] = mapped_column(String(255), nullable=False)
    volume_format: Mapped[str] = mapped_column(String(16), nullable=False)
    pool_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    pool_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    volume_generation: Mapped[int | None] = mapped_column(Integer)
    volume_hash: Mapped[str | None] = mapped_column(String(64))
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    current_xml: Mapped[bytes | None] = mapped_column(LargeBinary)
    proposed_xml: Mapped[bytes | None] = mapped_column(LargeBinary)
    diff_text: Mapped[str] = mapped_column(Text, nullable=False)
    confirmation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
