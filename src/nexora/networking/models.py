"""Persistent network change plan model."""

from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class NetworkChangePlan(Base):
    __tablename__ = "network_change_plans"

    id: Mapped[str] = mapped_column(primary_key=True)
    host_id: Mapped[str] = mapped_column(nullable=False)
    change_type: Mapped[str] = mapped_column(nullable=False)
    target_iface: Mapped[str] = mapped_column(nullable=False)
    change_input_json: Mapped[str] = mapped_column(default="{}")
    rollback_script: Mapped[str] = mapped_column(nullable=False)
    confirmation_digest: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(default="preview")
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    confirmed_at: Mapped[datetime | None] = mapped_column(default=None)
    confirmation_deadline: Mapped[datetime | None] = mapped_column(default=None)
