"""Add persistent storage pool change plans.

Revision ID: 20260728_0011
Revises: 20260728_0010
Create Date: 2026-07-28 00:00:10
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0011"
down_revision = "20260728_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_pool_change_plans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("pool_resource_id", sa.String(36)),
        sa.Column("pool_uuid", sa.String(36), nullable=False),
        sa.Column("pool_name", sa.String(128), nullable=False),
        sa.Column("pool_type", sa.String(16), nullable=False),
        sa.Column("base_generation", sa.Integer()),
        sa.Column("base_persistent_hash", sa.String(64)),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("current_xml", sa.LargeBinary()),
        sa.Column("proposed_xml", sa.LargeBinary()),
        sa.Column("proposed_hash", sa.String(64)),
        sa.Column("diff_text", sa.Text(), nullable=False),
        sa.Column("confirmation_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["hosts.id"],
            name="fk_storage_pool_change_plans_host_id_hosts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_storage_pool_change_plans"),
    )
    op.create_index(
        "ix_storage_pool_change_plans_host_id",
        "storage_pool_change_plans",
        ["host_id"],
    )


def downgrade() -> None:
    op.drop_table("storage_pool_change_plans")
