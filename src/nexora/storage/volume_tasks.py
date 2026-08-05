"""Persistent storage volume task contracts and handlers."""

import json
from dataclasses import dataclass
from uuid import UUID

from nexora.storage.volume_mutations import StorageVolumeMutationService
from nexora.storage.volume_service import StorageVolumeService
from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus


@dataclass(frozen=True)
class StorageVolumeTaskInput:
    plan_id: str
    host_id: str
    pool_uuid: str
    operation: str
    resource_id: str | None = None

    def encode(self) -> str:
        return json.dumps(vars(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str | None) -> "StorageVolumeTaskInput":
        if value is None or len(value) > 2_048:
            raise ValueError("storage volume task input is unavailable")
        try:
            payload = json.loads(value)
            result = cls(
                str(payload["plan_id"]),
                str(payload["host_id"]),
                str(UUID(str(payload["pool_uuid"]))),
                str(payload["operation"]),
                (str(payload["resource_id"]) if payload.get("resource_id") is not None else None),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("storage volume task input is invalid") from exc
        if (
            not result.plan_id
            or not result.host_id
            or result.operation not in {"create", "resize", "delete"}
            or (result.operation in {"resize", "delete"} and not result.resource_id)
        ):
            raise ValueError("storage volume task input is invalid")
        return result


@dataclass
class StorageVolumeChangeHandler:
    create_service: StorageVolumeService
    mutation_service: StorageVolumeMutationService

    def __call__(self, context: TaskContext, task: Task) -> str:
        task_input = StorageVolumeTaskInput.decode(task.input_summary)
        expected_resource_id = task_input.resource_id or task_input.pool_uuid
        if (
            task.host_id != task_input.host_id
            or task.resource_id != expected_resource_id
            or task.task_type != "storage.volume_change"
        ):
            raise ValueError("storage volume task scope does not match input")
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
            service = (
                self.create_service.execute_create
                if task_input.operation == "create"
                else self.mutation_service.execute
            )
            summary = service(task_input.plan_id, task_id=task.id, progress=progress)
        except Exception:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.FAILED)
            raise
        if active_step is not None:
            context.finish_step(active_step)
        return summary
