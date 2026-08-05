"""Persistent confirmation plans for platform-image VM creation."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class VmMediaCreationPlan(Base):
    __tablename__ = "vm_media_creation_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host_id: Mapped[str] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_item_id: Mapped[str] = mapped_column(
        ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False
    )
    vm_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    vm_name: Mapped[str] = mapped_column(String(128), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_xml: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    diff_text: Mapped[str] = mapped_column(Text, nullable=False)
    confirmation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_resource_id: Mapped[str | None] = mapped_column(String(36))
    resized_image_sha256: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
