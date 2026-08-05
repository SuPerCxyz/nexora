"""Add persistent blank-disk VM creation plans.

Revision ID: 20260803_0021
Revises: 20260731_0020
Create Date: 2026-08-03 09:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260803_0021"
down_revision = "20260731_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vm_blank_creation_plans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("vm_uuid", sa.String(36), nullable=False),
        sa.Column("vm_name", sa.String(128), nullable=False),
        sa.Column("disk_name", sa.String(255), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("volume_xml", sa.LargeBinary(), nullable=False),
        sa.Column("proposed_xml", sa.LargeBinary(), nullable=False),
        sa.Column("diff_text", sa.Text(), nullable=False),
        sa.Column("confirmation_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("result_resource_id", sa.String(36)),
        sa.Column("error_message", sa.Text()),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vm_blank_creation_plans_host_id", "vm_blank_creation_plans", ["host_id"])


def downgrade() -> None:
    op.drop_table("vm_blank_creation_plans")
