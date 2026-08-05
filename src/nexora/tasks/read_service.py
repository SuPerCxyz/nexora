"""Bounded read queries for task coordination and pages."""

from dataclasses import dataclass

from sqlalchemy import select

from nexora.db import Database
from nexora.tasks.models import Task, TaskStatus, TaskStep

ACTIVE_TASK_STATUSES = (
    TaskStatus.PENDING,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.WAITING_CONFIRMATION,
    TaskStatus.CANCEL_REQUESTED,
    TaskStatus.RECOVERING,
)


@dataclass(frozen=True)
class TaskDetail:
    task: Task
    steps: list[TaskStep]


class TaskReadService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def find_active(
        self,
        task_type: str,
        *,
        host_id: str | None = None,
        vm_uuid: str | None = None,
    ) -> Task | None:
        statement = (
            select(Task)
            .where(
                Task.task_type == task_type,
                Task.status.in_(ACTIVE_TASK_STATUSES),
            )
            .order_by(Task.created_at)
            .limit(1)
        )
        if host_id is not None:
            statement = statement.where(Task.host_id == host_id)
        if vm_uuid is not None:
            statement = statement.where(Task.vm_uuid == vm_uuid)
        with self.database.session() as session:
            return session.scalar(statement)

    def recent(self, *, limit: int = 200) -> list[Task]:
        if not 1 <= limit <= 500:
            raise ValueError("invalid task result limit")
        with self.database.session() as session:
            return list(
                session.scalars(select(Task).order_by(Task.created_at.desc(), Task.id).limit(limit))
            )

    def find_active_vm_write(self, host_id: str, vm_uuid: str) -> Task | None:
        """Return any active VM-scoped write task for coarse enqueue serialization."""

        statement = (
            select(Task)
            .where(
                Task.host_id == host_id,
                Task.vm_uuid == vm_uuid,
                Task.task_type.like("vm.%"),
                Task.status.in_(ACTIVE_TASK_STATUSES),
            )
            .order_by(Task.created_at)
            .limit(1)
        )
        with self.database.session() as session:
            return session.scalar(statement)

    def detail(self, task_id: str) -> TaskDetail | None:
        with self.database.session() as session:
            task = session.get(Task, task_id)
            if task is None:
                return None
            steps = list(
                session.scalars(
                    select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.sequence)
                )
            )
            return TaskDetail(task, steps)
