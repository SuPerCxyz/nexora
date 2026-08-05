"""Persistent, confirmation-bound virtual machine XML change plans."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class VmChangePlanStatus(StrEnum):
    PREVIEW = "preview"
    CONFIRMED = "confirmed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class VmChangePlan(Base):
    __tablename__ = "vm_change_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host_id: Mapped[str] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_index_id: Mapped[str] = mapped_column(
        ForeignKey("resource_indexes.id", ondelete="CASCADE"), nullable=False
    )
    vm_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    base_persistent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_xml: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    proposed_xml: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    proposed_persistent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_input_json: Mapped[str] = mapped_column(Text, nullable=False)
    diff_text: Mapped[str] = mapped_column(Text, nullable=False)
    confirmation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
