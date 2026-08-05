"""Persistent storage pool operation task handlers."""

from dataclasses import dataclass

from nexora.storage.delete_service import StoragePoolDeleteService
from nexora.storage.lifecycle import StoragePoolLifecycleService
from nexora.storage.service import StoragePoolService
from nexora.storage.task_contracts import StoragePoolLifecycleInput, StoragePoolTaskInput
from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus


@dataclass
class StoragePoolChangeHandler:
    service: StoragePoolService
    delete_service: StoragePoolDeleteService

    def __call__(self, context: TaskContext, task: Task) -> str:
        task_input = StoragePoolTaskInput.decode(task.input_summary)
        if (
            task.host_id != task_input.host_id
            or task.resource_id != task_input.pool_uuid
            or task.task_type != "storage.pool_change"
        ):
            raise ValueError("storage pool task scope does not match input")
        active_step: int | None = None

        def progress(sequence: int, message: str) -> None:
            nonlocal active_step
            if active_step is not None:
                context.finish_step(active_step)
            context.start_step(sequence, message)
            active_step = sequence
            context.checkpoint(
                progress=(sequence - 1) / 4 * 100,
                current_step=sequence,
                message=message,
            )

        try:
            if task_input.operation == "create":
                summary = self.service.execute_create(
                    task_input.plan_id,
                    task_id=task.id,
                    progress=progress,
                )
            else:
                summary = self.delete_service.execute(
                    task_input.plan_id,
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


@dataclass
class StoragePoolLifecycleHandler:
    service: StoragePoolLifecycleService

    def __call__(self, context: TaskContext, task: Task) -> str:
        task_input = StoragePoolLifecycleInput.decode(task.input_summary)
        if (
            task.host_id != task_input.base.host_id
            or task.resource_id != task_input.base.native_id
            or task.task_type != "storage.pool_lifecycle"
        ):
            raise ValueError("storage lifecycle task scope does not match input")
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
                task_input,
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
