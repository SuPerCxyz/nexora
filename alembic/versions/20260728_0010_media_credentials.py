"""Add revocable media access credentials.

Revision ID: 20260728_0010
Revises: 20260728_0009
Create Date: 2026-07-28 00:00:09
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0010"
down_revision = "20260728_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_credentials",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("media_item_id", sa.String(36), nullable=False),
        sa.Column("media_sha256", sa.String(64), nullable=False),
        sa.Column("host_id", sa.String(36)),
        sa.Column("vm_uuid", sa.String(36)),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["hosts.id"],
            name="fk_media_credentials_host_id_hosts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["media_item_id"],
            ["media_items.id"],
            name="fk_media_credentials_media_item_id_media_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_media_credentials"),
        sa.UniqueConstraint("token_digest", name="uq_media_credentials_token_digest"),
    )
    op.create_index(
        "ix_media_credentials_media_item_id",
        "media_credentials",
        ["media_item_id"],
    )
    op.create_index(
        "ix_media_credentials_host_id",
        "media_credentials",
        ["host_id"],
    )


def downgrade() -> None:
    op.drop_table("media_credentials")
