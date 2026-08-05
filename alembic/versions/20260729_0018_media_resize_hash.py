"""Persist post-resize image verification hash.

Revision ID: 20260729_0018
Revises: 20260729_0017
Create Date: 2026-07-29 08:30:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260729_0018"
down_revision = "20260729_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vm_media_creation_plans",
        sa.Column("resized_image_sha256", sa.String(64)),
    )


def downgrade() -> None:
    with op.batch_alter_table("vm_media_creation_plans") as batch:
        batch.drop_column("resized_image_sha256")
