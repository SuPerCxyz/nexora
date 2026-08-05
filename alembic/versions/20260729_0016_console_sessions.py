"""Add one-time console sessions.

Revision ID: 20260729_0016
Revises: 20260729_0015
Create Date: 2026-07-29 07:10:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260729_0016"
down_revision = "20260729_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "console_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("administrator_session_hash", sa.String(64), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("vm_uuid", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("last_activity_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_console_sessions_status_expires",
        "console_sessions",
        ["status", "expires_at"],
    )
    op.create_index(
        "ix_console_sessions_host_vm",
        "console_sessions",
        ["host_id", "vm_uuid"],
    )


def downgrade() -> None:
    op.drop_table("console_sessions")
