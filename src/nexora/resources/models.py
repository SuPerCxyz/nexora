"""Node-scoped resource index and scan models."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nexora.db.base import Base


class ResourceType(StrEnum):
    VIRTUAL_MACHINE = "virtual_machine"
    SNAPSHOT = "snapshot"
    STORAGE_POOL = "storage_pool"
    STORAGE_VOLUME = "storage_volume"
    LIBVIRT_NETWORK = "libvirt_network"
    HOST_INTERFACE = "host_interface"
    PCI_DEVICE = "pci_device"
    USB_DEVICE = "usb_device"


class ResourceStatus(StrEnum):
    MANAGED = "managed"
    READ_ONLY = "read_only"
    PARTIALLY_SUPPORTED = "partially_supported"
    TRANSIENT = "transient"
    INACCESSIBLE = "inaccessible"
    UNSUPPORTED = "unsupported"
    MISSING = "missing"
    STALE = "stale"
    CHANGED_OUT_OF_BAND = "changed_out_of_band"
    CONFLICT = "conflict"


class ScanStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ResourceScan(Base):
    __tablename__ = "resource_scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(48), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "uq_resource_scans_generation",
            "host_id",
            "resource_type",
            "generation",
            unique=True,
        ),
    )


class ResourceIndex(Base):
    __tablename__ = "resource_indexes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(48), nullable=False)
    native_id: Mapped[str] = mapped_column(String(512), nullable=False)
    parent_native_id: Mapped[str | None] = mapped_column(String(512))
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    persistent_hash: Mapped[str | None] = mapped_column(String(64))
    live_hash: Mapped[str | None] = mapped_column(String(64))
    hash_algorithm: Mapped[str | None] = mapped_column(String(64))
    observed_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)
    labels_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    notes: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_resource_indexes_identity",
            "host_id",
            "resource_type",
            "native_id",
            unique=True,
        ),
        Index("ix_resource_indexes_host_type", "host_id", "resource_type"),
    )


class ResourceDocument(Base):
    __tablename__ = "resource_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_index_id: Mapped[str] = mapped_column(
        ForeignKey("resource_indexes.id", ondelete="CASCADE"), nullable=False
    )
    document_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash_algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "uq_resource_documents_kind",
            "resource_index_id",
            "document_kind",
            unique=True,
        ),
    )
