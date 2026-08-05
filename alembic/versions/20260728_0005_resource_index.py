"""Add node-scoped resource scan, index, and document caches.

Revision ID: 20260728_0005
Revises: 20260728_0004
Create Date: 2026-07-28 00:00:04
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0005"
down_revision = "20260728_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_scans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("resource_type", sa.String(48), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["hosts.id"],
            name="fk_resource_scans_host_id_hosts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resource_scans"),
    )
    op.create_index(
        "uq_resource_scans_generation",
        "resource_scans",
        ["host_id", "resource_type", "generation"],
        unique=True,
    )
    op.create_table(
        "resource_indexes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("resource_type", sa.String(48), nullable=False),
        sa.Column("native_id", sa.String(512), nullable=False),
        sa.Column("parent_native_id", sa.String(512)),
        sa.Column("display_name", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("persistent_hash", sa.String(64)),
        sa.Column("live_hash", sa.String(64)),
        sa.Column("hash_algorithm", sa.String(64)),
        sa.Column("observed_generation", sa.Integer(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("labels_json", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("missing_since", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["hosts.id"],
            name="fk_resource_indexes_host_id_hosts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resource_indexes"),
    )
    op.create_index(
        "uq_resource_indexes_identity",
        "resource_indexes",
        ["host_id", "resource_type", "native_id"],
        unique=True,
    )
    op.create_index(
        "ix_resource_indexes_host_type",
        "resource_indexes",
        ["host_id", "resource_type"],
    )
    op.create_table(
        "resource_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resource_index_id", sa.String(36), nullable=False),
        sa.Column("document_kind", sa.String(32), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("hash_algorithm", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["resource_index_id"],
            ["resource_indexes.id"],
            name="fk_resource_documents_resource_index_id_resource_indexes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resource_documents"),
    )
    op.create_index(
        "uq_resource_documents_kind",
        "resource_documents",
        ["resource_index_id", "document_kind"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("resource_documents")
    op.drop_table("resource_indexes")
    op.drop_table("resource_scans")
