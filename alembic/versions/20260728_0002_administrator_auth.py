"""Add single-administrator authentication.

Revision ID: 20260728_0002
Revises: 20260728_0001
Create Date: 2026-07-28 00:00:01
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0002"
down_revision = "20260728_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "administrators",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("session_timeout_minutes", sa.Integer(), nullable=False),
        sa.Column("global_monospace", sa.Boolean(), nullable=False),
        sa.Column("density", sa.String(16), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_administrators"),
        sa.UniqueConstraint("username", name="uq_administrators_username"),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("administrator_id", sa.Integer(), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["administrator_id"],
            ["administrators.id"],
            name="fk_admin_sessions_administrator_id_administrators",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash", name="pk_admin_sessions"),
    )
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("remote_address", sa.String(64), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_login_attempts_occurred_at", "login_attempts", ["occurred_at"])
    op.create_index(
        "ix_login_attempts_identity",
        "login_attempts",
        ["username", "remote_address", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_table("admin_sessions")
    op.drop_table("administrators")
