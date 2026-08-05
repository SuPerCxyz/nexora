"""Establish the initial schema baseline.

Revision ID: 20260728_0001
Revises:
Create Date: 2026-07-28 00:00:00
"""

revision = "20260728_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the empty P0 schema baseline."""


def downgrade() -> None:
    """Remove the empty P0 schema baseline."""
