"""Add persistent host removal plans and tombstones.

Revision ID: 20260728_0006
Revises: 20260728_0005
Create Date: 2026-07-28 00:00:05
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0006"
down_revision = "20260728_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "host_removal_plans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("host_name", sa.String(128), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("original_host_status", sa.String(32), nullable=False),
        sa.Column("remote_paths_json", sa.Text(), nullable=False),
        sa.Column("remote_units_json", sa.Text(), nullable=False),
        sa.Column("warnings_json", sa.Text(), nullable=False),
        sa.Column("confirmation_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.PrimaryKeyConstraint("id", name="pk_host_removal_plans"),
    )
    op.create_index(
        "ix_host_removal_plans_host_id",
        "host_removal_plans",
        ["host_id"],
    )
    op.create_table(
        "host_removal_tombstones",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("original_host_id", sa.String(36), nullable=False),
        sa.Column("host_name", sa.String(128), nullable=False),
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column("ssh_port", sa.Integer(), nullable=False),
        sa.Column("fingerprints_json", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("cleanup_summary_json", sa.Text(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_host_removal_tombstones"),
    )
    op.create_index(
        "ix_host_removal_tombstones_original_host_id",
        "host_removal_tombstones",
        ["original_host_id"],
    )


def downgrade() -> None:
    op.drop_table("host_removal_tombstones")
    op.drop_table("host_removal_plans")
