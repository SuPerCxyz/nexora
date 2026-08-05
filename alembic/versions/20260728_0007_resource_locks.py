"""Add database-backed resource write locks.

Revision ID: 20260728_0007
Revises: 20260728_0006
Create Date: 2026-07-28 00:00:06
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0007"
down_revision = "20260728_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_locks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(512), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["hosts.id"],
            name="fk_resource_locks_host_id_hosts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resource_locks"),
    )
    op.create_index(
        "uq_resource_locks_identity",
        "resource_locks",
        ["host_id", "resource_type", "resource_id"],
        unique=True,
    )
    op.create_index(
        "ix_resource_locks_expiry",
        "resource_locks",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_table("resource_locks")
