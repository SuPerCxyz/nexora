"""Add VM metrics history and network change plans.

Revision ID: 20260730_0019
Revises: 20260729_0018
Create Date: 2026-07-30 12:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260730_0019"
down_revision = "20260729_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vm_metrics_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("vm_uuid", sa.String(36), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(32)),
        sa.Column("cpu_time_ns", sa.BigInteger),
        sa.Column("cpu_usage_percent", sa.Float),
        sa.Column("memory_usage_kib", sa.BigInteger),
        sa.Column("disk_read_bytes", sa.BigInteger),
        sa.Column("disk_write_bytes", sa.BigInteger),
        sa.Column("net_rx_bytes", sa.BigInteger),
        sa.Column("net_tx_bytes", sa.BigInteger),
    )
    op.create_index(
        "ix_vm_metrics_history_host_vm_time",
        "vm_metrics_history",
        ["host_id", "vm_uuid", "sampled_at"],
    )
    op.create_table(
        "network_change_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("change_type", sa.String(32), nullable=False),
        sa.Column("target_iface", sa.String(64), nullable=False),
        sa.Column("change_input_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("rollback_script", sa.Text, nullable=False),
        sa.Column("confirmation_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("confirmation_deadline", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("network_change_plans")
    op.drop_index("ix_vm_metrics_history_host_vm_time", table_name="vm_metrics_history")
    op.drop_table("vm_metrics_history")
