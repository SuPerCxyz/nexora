"""Add persistent VM Snapshot change plans.

Revision ID: 20260729_0013
Revises: 20260728_0012
Create Date: 2026-07-29 00:00:12
"""

import sqlalchemy as sa

from alembic import op

revision = "20260729_0013"
down_revision = "20260728_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "snapshot_change_plans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("vm_resource_id", sa.String(36), nullable=False),
        sa.Column("vm_uuid", sa.String(36), nullable=False),
        sa.Column("snapshot_name", sa.String(128), nullable=False),
        sa.Column("vm_generation", sa.Integer(), nullable=False),
        sa.Column("vm_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_resource_id", sa.String(36)),
        sa.Column("snapshot_generation", sa.Integer()),
        sa.Column("snapshot_hash", sa.String(64)),
        sa.Column("input_json", sa.Text(), nullable=False),
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
            name="fk_snapshot_change_plans_host_id_hosts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_snapshot_change_plans"),
    )
    op.create_index(
        "ix_snapshot_change_plans_host_id",
        "snapshot_change_plans",
        ["host_id"],
    )


def downgrade() -> None:
    op.drop_table("snapshot_change_plans")
