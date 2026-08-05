"""Managed host connection, trust, and capability models."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class HostStatus(StrEnum):
    PENDING_HOST_KEY = "pending_host_key"
    READY = "ready"
    SCANNING = "scanning"
    DEGRADED = "degraded"
    INACCESSIBLE = "inaccessible"
    REMOVAL_PENDING = "removal_pending"


class AuthenticationMethod(StrEnum):
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"


class SudoMode(StrEnum):
    NONE = "none"
    PASSWORDLESS = "passwordless"


class Host(Base):
    """A remote Linux KVM/libvirt node."""

    __tablename__ = "hosts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    ssh_port: Mapped[int] = mapped_column(Integer, nullable=False)
    ssh_username: Mapped[str] = mapped_column(String(64), nullable=False)
    authentication_method: Mapped[str] = mapped_column(String(32), nullable=False)
    sudo_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    libvirt_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    pending_host_key_digest: Mapped[str | None] = mapped_column(String(64))
    labels_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    notes: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("uq_hosts_endpoint", "address", "ssh_port", unique=True),)


class HostCredential(Base):
    """One resource-bound encrypted credential envelope."""

    __tablename__ = "host_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host_id: Mapped[str] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    authentication_method: Mapped[str] = mapped_column(String(32), nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    nonce: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HostFingerprint(Base):
    """Discovered and historical SSH Host Key material."""

    __tablename__ = "host_fingerprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[str] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
    )
    key_type: Mapped[str] = mapped_column(String(64), nullable=False)
    key_data: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    trust_state: Mapped[str] = mapped_column(String(16), nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trusted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_host_fingerprints_identity",
            "host_id",
            "key_type",
            "fingerprint",
            unique=True,
        ),
    )


class HostCapability(Base):
    """Latest bounded result for one read-only host capability check."""

    __tablename__ = "host_capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[str] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
    )
    capability_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    value_json: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "uq_host_capabilities_key",
            "host_id",
            "capability_key",
            unique=True,
        ),
    )
