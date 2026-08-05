"""Durable task-step lifecycle operations."""

from datetime import UTC, datetime

from sqlalchemy import select

from nexora.db import Database
from nexora.tasks.models import Task, TaskStatus, TaskStep, TaskStepStatus


class TaskStepStore:
    """Persist step boundaries only while a worker owns the task lease."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def start(
        self,
        task_id: str,
        owner: str,
        *,
        sequence: int,
        name: str,
        command_summary: str | None = None,
    ) -> bool:
        if sequence < 1 or not name or len(name) > 128:
            raise ValueError("invalid task step")
        with self.database.session() as session:
            task = session.get(Task, task_id)
            if not _lease_allows_step(task, owner):
                return False
            assert task is not None
            if task.total_steps and sequence > task.total_steps:
                raise ValueError("task step exceeds total steps")
            step = session.scalar(
                select(TaskStep).where(
                    TaskStep.task_id == task_id,
                    TaskStep.sequence == sequence,
                )
            )
            now = datetime.now(UTC)
            if step is None:
                step = TaskStep(
                    task_id=task_id,
                    sequence=sequence,
                    name=name,
                    status=TaskStepStatus.RUNNING,
                    started_at=now,
                    attempt_count=1,
                    command_summary=command_summary,
                )
                session.add(step)
            else:
                step.name = name
                step.status = TaskStepStatus.RUNNING
                step.started_at = now
                step.finished_at = None
                step.attempt_count += 1
                step.command_summary = command_summary
                step.error_code = None
            task.current_step = sequence
            task.message = name
            return True

    def finish(
        self,
        task_id: str,
        owner: str,
        *,
        sequence: int,
        status: TaskStepStatus,
        stdout_summary: str | None = None,
        stderr_summary: str | None = None,
        error_code: str | None = None,
        checkpoint_data: str | None = None,
    ) -> bool:
        if status not in {
            TaskStepStatus.SUCCEEDED,
            TaskStepStatus.FAILED,
            TaskStepStatus.CANCELLED,
        }:
            raise ValueError("invalid terminal task step status")
        with self.database.session() as session:
            task = session.get(Task, task_id)
            if not _lease_allows_step(task, owner, allow_cancel=True):
                return False
            step = session.scalar(
                select(TaskStep).where(
                    TaskStep.task_id == task_id,
                    TaskStep.sequence == sequence,
                    TaskStep.status == TaskStepStatus.RUNNING,
                )
            )
            if step is None:
                return False
            step.status = status
            step.finished_at = datetime.now(UTC)
            step.stdout_summary = stdout_summary
            step.stderr_summary = stderr_summary
            step.error_code = error_code
            step.checkpoint_data = checkpoint_data
            return True


def _lease_allows_step(
    task: Task | None,
    owner: str,
    *,
    allow_cancel: bool = False,
) -> bool:
    if task is None or task.lease_owner != owner:
        return False
    allowed = {TaskStatus.RUNNING}
    if allow_cancel:
        allowed.add(TaskStatus.CANCEL_REQUESTED)
    return task.status in allowed
