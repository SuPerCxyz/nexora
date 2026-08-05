"""Add persistent shutdown full clone plans.

Revision ID: 20260729_0017
Revises: 20260729_0016
Create Date: 2026-07-29 08:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260729_0017"
down_revision = "20260729_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vm_clone_plans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source_host_id", sa.String(36), nullable=False),
        sa.Column("source_vm_uuid", sa.String(36), nullable=False),
        sa.Column("target_host_id", sa.String(36), nullable=False),
        sa.Column("target_vm_uuid", sa.String(36), nullable=False),
        sa.Column("target_name", sa.String(128), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("source_xml", sa.LargeBinary(), nullable=False),
        sa.Column("target_xml", sa.LargeBinary(), nullable=False),
        sa.Column("diff_text", sa.Text(), nullable=False),
        sa.Column("confirmation_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("result_resource_id", sa.String(36)),
        sa.Column("error_message", sa.Text()),
        sa.ForeignKeyConstraint(["source_host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vm_clone_plans_source_host_id", "vm_clone_plans", ["source_host_id"])
    op.create_index("ix_vm_clone_plans_target_host_id", "vm_clone_plans", ["target_host_id"])


def downgrade() -> None:
    op.drop_table("vm_clone_plans")
