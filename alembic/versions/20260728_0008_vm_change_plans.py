"""Add persistent virtual machine XML change plans.

Revision ID: 20260728_0008
Revises: 20260728_0007
Create Date: 2026-07-28 00:00:07
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0008"
down_revision = "20260728_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vm_change_plans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("resource_index_id", sa.String(36), nullable=False),
        sa.Column("vm_uuid", sa.String(36), nullable=False),
        sa.Column("change_type", sa.String(32), nullable=False),
        sa.Column("base_generation", sa.Integer(), nullable=False),
        sa.Column("base_persistent_hash", sa.String(64), nullable=False),
        sa.Column("original_xml", sa.LargeBinary(), nullable=False),
        sa.Column("proposed_xml", sa.LargeBinary(), nullable=False),
        sa.Column("proposed_persistent_hash", sa.String(64), nullable=False),
        sa.Column("change_input_json", sa.Text(), nullable=False),
        sa.Column("diff_text", sa.Text(), nullable=False),
        sa.Column("confirmation_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["hosts.id"],
            name="fk_vm_change_plans_host_id_hosts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resource_index_id"],
            ["resource_indexes.id"],
            name="fk_vm_change_plans_resource_index_id_resource_indexes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vm_change_plans"),
    )
    op.create_index("ix_vm_change_plans_host_id", "vm_change_plans", ["host_id"])


def downgrade() -> None:
    op.drop_table("vm_change_plans")
