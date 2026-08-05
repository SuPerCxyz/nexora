"""Add managed hosts, encrypted credentials, trust, and capabilities.

Revision ID: 20260728_0004
Revises: 20260728_0003
Create Date: 2026-07-28 00:00:03
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0004"
down_revision = "20260728_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column("ssh_port", sa.Integer(), nullable=False),
        sa.Column("ssh_username", sa.String(64), nullable=False),
        sa.Column("authentication_method", sa.String(32), nullable=False),
        sa.Column("sudo_mode", sa.String(32), nullable=False),
        sa.Column("libvirt_uri", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("pending_host_key_digest", sa.String(64)),
        sa.Column("labels_json", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_connected_at", sa.DateTime(timezone=True)),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_hosts"),
        sa.UniqueConstraint("name", name="uq_hosts_name"),
    )
    op.create_index(
        "uq_hosts_endpoint",
        "hosts",
        ["address", "ssh_port"],
        unique=True,
    )
    op.create_table(
        "host_credentials",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("authentication_method", sa.String(32), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["hosts.id"],
            name="fk_host_credentials_host_id_hosts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_host_credentials"),
        sa.UniqueConstraint("host_id", name="uq_host_credentials_host_id"),
    )
    op.create_table(
        "host_fingerprints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("key_type", sa.String(64), nullable=False),
        sa.Column("key_data", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("trust_state", sa.String(16), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trusted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["hosts.id"],
            name="fk_host_fingerprints_host_id_hosts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_host_fingerprints"),
    )
    op.create_index(
        "uq_host_fingerprints_identity",
        "host_fingerprints",
        ["host_id", "key_type", "fingerprint"],
        unique=True,
    )
    op.create_table(
        "host_capabilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("capability_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("value_json", sa.Text()),
        sa.Column("detail", sa.Text()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["hosts.id"],
            name="fk_host_capabilities_host_id_hosts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_host_capabilities"),
    )
    op.create_index(
        "uq_host_capabilities_key",
        "host_capabilities",
        ["host_id", "capability_key"],
        unique=True,
    )
    op.create_table(
        "remote_command_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("command_summary", sa.Text(), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=False),
        sa.Column("timed_out", sa.Boolean(), nullable=False),
        sa.Column("cancelled", sa.Boolean(), nullable=False),
        sa.Column("stdout_summary", sa.Text(), nullable=False),
        sa.Column("stderr_summary", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_remote_command_logs"),
        sa.UniqueConstraint(
            "operation_id",
            name="uq_remote_command_logs_operation_id",
        ),
    )
    op.create_index(
        "ix_remote_command_logs_host_id",
        "remote_command_logs",
        ["host_id"],
    )


def downgrade() -> None:
    op.drop_table("remote_command_logs")
    op.drop_table("host_capabilities")
    op.drop_table("host_fingerprints")
    op.drop_table("host_credentials")
    op.drop_table("hosts")
