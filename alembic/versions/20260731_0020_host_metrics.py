"""Add bounded host metrics history.

Revision ID: 20260731_0020
Revises: 20260730_0019
Create Date: 2026-07-31 14:30:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260731_0020"
down_revision = "20260730_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "host_metrics_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("load_1", sa.Float),
        sa.Column("load_5", sa.Float),
        sa.Column("load_15", sa.Float),
        sa.Column("memory_total_kib", sa.BigInteger),
        sa.Column("memory_available_kib", sa.BigInteger),
        sa.Column("uptime_seconds", sa.BigInteger),
    )
    op.create_index(
        "ix_host_metrics_history_host_time",
        "host_metrics_history",
        ["host_id", "sampled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_host_metrics_history_host_time", table_name="host_metrics_history")
    op.drop_table("host_metrics_history")
