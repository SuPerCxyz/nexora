"""Persistent task handler for confirmed host removal plans."""

from dataclasses import dataclass

from nexora.hosts.removal import HostRemovalService
from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus


@dataclass
class HostRemovalHandler:
    service: HostRemovalService

    def __call__(self, context: TaskContext, task: Task) -> str:
        if task.resource_id is None:
            raise ValueError("host removal task has no plan")
        active_step: int | None = None

        def progress(sequence: int, message: str) -> None:
            nonlocal active_step
            if active_step is not None:
                context.finish_step(active_step)
            context.start_step(sequence, message)
            active_step = sequence
            context.checkpoint(
                progress=(sequence - 1) / 3 * 100,
                current_step=sequence,
                message=message,
            )

        try:
            summary = self.service.execute(
                task.resource_id,
                task_id=task.id,
                progress=progress,
            )
        except Exception:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.FAILED)
            raise
        if active_step is not None:
            context.finish_step(active_step)
        return summary
