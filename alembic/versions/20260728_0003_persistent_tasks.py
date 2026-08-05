"""Add persistent tasks and steps.

Revision ID: 20260728_0003
Revises: 20260728_0002
Create Date: 2026-07-28 00:00:02
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0003"
down_revision = "20260728_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("host_id", sa.String(128)),
        sa.Column("vm_uuid", sa.String(36)),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_id", sa.String(256)),
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.Column("idempotency_scope", sa.String(256), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("total_steps", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(512)),
        sa.Column("input_summary", sa.Text()),
        sa.Column("result_summary", sa.Text()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("resumable", sa.Boolean(), nullable=False),
        sa.Column("recovery_strategy", sa.String(32), nullable=False),
        sa.Column("checkpoint_data", sa.Text()),
        sa.Column("checkpoint_version", sa.Integer(), nullable=False),
        sa.Column("parent_task_id", sa.String(36)),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["parent_task_id"],
            ["tasks.id"],
            name="fk_tasks_parent_task_id_tasks",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
        sa.UniqueConstraint("operation_id", name="uq_tasks_operation_id"),
    )
    op.create_index(
        "uq_tasks_idempotency",
        "tasks",
        ["idempotency_scope", "idempotency_key"],
        unique=True,
    )
    op.create_index("ix_tasks_claim", "tasks", ["status", "created_at"])
    op.create_index("ix_tasks_lease", "tasks", ["status", "lease_expires_at"])
    op.create_table(
        "task_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("command_summary", sa.Text()),
        sa.Column("stdout_summary", sa.Text()),
        sa.Column("stderr_summary", sa.Text()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("checkpoint_data", sa.Text()),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name="fk_task_steps_task_id_tasks",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_task_steps"),
    )
    op.create_index(
        "uq_task_steps_sequence",
        "task_steps",
        ["task_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("task_steps")
    op.drop_table("tasks")
