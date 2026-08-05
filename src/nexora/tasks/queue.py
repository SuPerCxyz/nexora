"""Atomic SQLite task enqueue and lease claiming."""

from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from nexora.db import Database
from nexora.tasks.definitions import RECOVERY_STRATEGIES, TaskCreate
from nexora.tasks.models import Task, TaskStatus

TERMINAL_TASK_STATUSES = frozenset(
    (
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.TIMED_OUT,
        TaskStatus.UNKNOWN,
    )
)


class TaskQueue:
    """Persist and atomically lease tasks using short transactions."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def enqueue(self, create: TaskCreate) -> Task:
        if create.recovery_strategy not in RECOVERY_STRATEGIES:
            raise ValueError("invalid recovery strategy")
        if not 0 <= create.max_retries <= 10:
            raise ValueError("invalid maximum retry count")
        now = datetime.now(UTC)
        task = Task(
            id=str(uuid4()),
            operation_id=str(uuid4()),
            task_type=create.task_type,
            title=create.title,
            idempotency_scope=create.idempotency_scope,
            idempotency_key=create.idempotency_key,
            host_id=create.host_id,
            vm_uuid=create.vm_uuid,
            resource_type=create.resource_type,
            resource_id=create.resource_id,
            status=TaskStatus.PENDING,
            progress=0,
            current_step=0,
            total_steps=create.total_steps,
            input_summary=create.input_summary,
            created_at=now,
            cancel_requested=False,
            retry_count=0,
            max_retries=create.max_retries,
            resumable=create.resumable,
            recovery_strategy=create.recovery_strategy,
            checkpoint_version=1,
        )
        try:
            with self.database.session() as session:
                session.add(task)
                session.flush()
            return task
        except IntegrityError:
            with self.database.session() as session:
                existing = session.scalar(
                    select(Task).where(
                        Task.idempotency_scope == create.idempotency_scope,
                        Task.idempotency_key == create.idempotency_key,
                    )
                )
                if existing is None:
                    raise
                return existing

    def claim_next(
        self,
        owner: str,
        *,
        lease_seconds: int = 30,
        task_types: Collection[str] | None = None,
    ) -> Task | None:
        if not owner or not 5 <= lease_seconds <= 3_600:
            raise ValueError("invalid task lease")
        if task_types is not None and not task_types:
            return None
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=lease_seconds)
        candidate = (
            select(Task.id)
            .where(Task.status.in_((TaskStatus.PENDING, TaskStatus.QUEUED)))
            .order_by(Task.created_at, Task.id)
            .limit(1)
        )
        if task_types is not None:
            candidate = candidate.where(Task.task_type.in_(task_types))
        statement = (
            update(Task)
            .where(
                Task.id == candidate.scalar_subquery(),
                Task.status.in_((TaskStatus.PENDING, TaskStatus.QUEUED)),
            )
            .values(
                status=TaskStatus.RUNNING,
                lease_owner=owner,
                lease_expires_at=expires_at,
                heartbeat_at=now,
                started_at=func.coalesce(Task.started_at, now),
            )
            .returning(Task.id)
        )
        with self.database.session() as session:
            task_id = session.execute(statement).scalar_one_or_none()
            return session.get(Task, task_id) if task_id is not None else None

    def heartbeat(self, task_id: str, owner: str, *, lease_seconds: int = 30) -> bool:
        now = datetime.now(UTC)
        statement = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.lease_owner == owner,
                Task.status.in_((TaskStatus.RUNNING, TaskStatus.CANCEL_REQUESTED)),
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
        )
        with self.database.session() as session:
            result = session.execute(statement)
            return _rowcount(result) == 1

    def checkpoint(
        self,
        task_id: str,
        owner: str,
        *,
        progress: float,
        current_step: int,
        message: str | None = None,
        checkpoint_data: str | None = None,
    ) -> bool:
        if not 0 <= progress <= 100 or current_step < 0:
            raise ValueError("invalid task progress")
        statement = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.lease_owner == owner,
                Task.status == TaskStatus.RUNNING,
            )
            .values(
                progress=progress,
                current_step=current_step,
                message=message,
                checkpoint_data=checkpoint_data,
            )
        )
        with self.database.session() as session:
            return _rowcount(session.execute(statement)) == 1

    def request_cancel(self, task_id: str) -> bool:
        now = datetime.now(UTC)
        with self.database.session() as session:
            pending = session.execute(
                update(Task)
                .where(
                    Task.id == task_id,
                    Task.status.in_((TaskStatus.PENDING, TaskStatus.QUEUED)),
                )
                .values(
                    status=TaskStatus.CANCELLED,
                    cancel_requested=True,
                    finished_at=now,
                )
            )
            if _rowcount(pending) == 1:
                return True
            running = session.execute(
                update(Task)
                .where(Task.id == task_id, Task.status == TaskStatus.RUNNING)
                .values(status=TaskStatus.CANCEL_REQUESTED, cancel_requested=True)
            )
            return _rowcount(running) == 1

    def cancellation_requested(self, task_id: str) -> bool:
        statement = select(Task.cancel_requested).where(Task.id == task_id)
        with self.database.session() as session:
            return bool(session.scalar(statement))

    def recover_stale(self, *, now: datetime | None = None) -> int:
        recovery_time = now or datetime.now(UTC)
        statement = (
            update(Task)
            .where(
                Task.status.in_(
                    (TaskStatus.RUNNING, TaskStatus.RECOVERING, TaskStatus.CANCEL_REQUESTED)
                ),
                Task.lease_expires_at < recovery_time,
            )
            .values(
                status=TaskStatus.INTERRUPTED,
                lease_owner=None,
                lease_expires_at=None,
                message="Worker lease expired; external state verification required",
            )
        )
        with self.database.session() as session:
            return _rowcount(session.execute(statement))

    def recover_orphaned_on_startup(self) -> int:
        """Identify work owned by the previous single-container process."""

        statement = (
            update(Task)
            .where(
                Task.status.in_(
                    (TaskStatus.RUNNING, TaskStatus.RECOVERING, TaskStatus.CANCEL_REQUESTED)
                )
            )
            .values(
                status=TaskStatus.INTERRUPTED,
                lease_owner=None,
                lease_expires_at=None,
                message="Previous process stopped; external state verification required",
            )
        )
        with self.database.session() as session:
            return _rowcount(session.execute(statement))

    def request_recovery(self, task_id: str) -> bool:
        """Queue an explicitly approved retry of an interrupted resumable task."""

        statement = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.status == TaskStatus.INTERRUPTED,
                Task.resumable.is_(True),
                Task.cancel_requested.is_(False),
                Task.retry_count < Task.max_retries,
                Task.recovery_strategy.in_(("resume_from_checkpoint", "retry_from_start")),
            )
            .values(
                status=TaskStatus.QUEUED,
                retry_count=Task.retry_count + 1,
                message="Recovery queued; authoritative external state will be verified",
                error_code=None,
                error_message=None,
                finished_at=None,
                lease_owner=None,
                lease_expires_at=None,
            )
        )
        with self.database.session() as session:
            return _rowcount(session.execute(statement)) == 1

    def interrupt_owned(self, owner: str, *, message: str) -> int:
        """Release this process's leases without replaying unfinished work."""

        statement = (
            update(Task)
            .where(
                Task.lease_owner == owner,
                Task.status.in_(
                    (TaskStatus.RUNNING, TaskStatus.RECOVERING, TaskStatus.CANCEL_REQUESTED)
                ),
            )
            .values(
                status=TaskStatus.INTERRUPTED,
                lease_owner=None,
                lease_expires_at=None,
                message=message,
            )
        )
        with self.database.session() as session:
            return _rowcount(session.execute(statement))

    def finish(
        self,
        task_id: str,
        owner: str,
        status: TaskStatus,
        *,
        result_summary: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        if status not in TERMINAL_TASK_STATUSES:
            raise ValueError("invalid terminal task status")
        statement = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.lease_owner == owner,
                Task.status.in_((TaskStatus.RUNNING, TaskStatus.CANCEL_REQUESTED)),
            )
            .values(
                status=status,
                progress=100 if status == TaskStatus.SUCCEEDED else Task.progress,
                result_summary=result_summary,
                error_message=error_message,
                finished_at=datetime.now(UTC),
                lease_owner=None,
                lease_expires_at=None,
            )
        )
        with self.database.session() as session:
            return _rowcount(session.execute(statement)) == 1


def _rowcount(result: object) -> int:
    return cast(CursorResult[Any], result).rowcount
