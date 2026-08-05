"""Add platform media scan and index tables.

Revision ID: 20260728_0009
Revises: 20260728_0008
Create Date: 2026-07-28 00:00:08
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0009"
down_revision = "20260728_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_scans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.PrimaryKeyConstraint("id", name="pk_media_scans"),
        sa.UniqueConstraint("generation", name="uq_media_scans_generation"),
    )
    op.create_table(
        "media_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("relative_path", sa.String(2048), nullable=False),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("modified_ns", sa.Integer(), nullable=False),
        sa.Column("file_device", sa.Integer(), nullable=False),
        sa.Column("file_inode", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("image_format", sa.String(32)),
        sa.Column("virtual_size_bytes", sa.Integer()),
        sa.Column("backing_chain_json", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(64)),
        sa.Column("architecture", sa.String(32)),
        sa.Column("notes", sa.Text()),
        sa.Column("observed_generation", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("missing_since", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_media_items"),
    )
    op.create_index(
        "uq_media_items_relative_path",
        "media_items",
        ["relative_path"],
        unique=True,
    )
    op.create_index(
        "ix_media_items_kind_status",
        "media_items",
        ["kind", "status"],
    )


def downgrade() -> None:
    op.drop_table("media_items")
    op.drop_table("media_scans")
