"""Add persistent VM configuration XML history for rollback.

Revision ID: 20260803_0023
Revises: 20260803_0022
Create Date: 2026-08-05 12:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260803_0023"
down_revision = "20260803_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vm_xml_history",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("vm_uuid", sa.String(36), nullable=False),
        sa.Column("xml", sa.Text(), nullable=False),
        sa.Column("xml_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_vm_xml_history_vm", "vm_xml_history", ["host_id", "vm_uuid"]
    )


def downgrade() -> None:
    op.drop_index("ix_vm_xml_history_vm", table_name="vm_xml_history")
    op.drop_table("vm_xml_history")
