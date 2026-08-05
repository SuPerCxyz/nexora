"""Persistent task handler for platform-image VM creation."""

import json
from dataclasses import dataclass
from uuid import UUID

from nexora.media.copy_errors import MediaCopyCancelled
from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus
from nexora.vms.media_creation_service import VmMediaCreationService


@dataclass(frozen=True)
class VmMediaCreationTaskInput:
    plan_id: str
    host_id: str
    vm_uuid: str

    def encode(self) -> str:
        return json.dumps(vars(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str | None) -> "VmMediaCreationTaskInput":
        if value is None or len(value) > 1_024:
            raise ValueError("platform-image VM task input is unavailable")
        try:
            payload = json.loads(value)
            result = cls(
                str(payload["plan_id"]),
                str(payload["host_id"]),
                str(UUID(str(payload["vm_uuid"]))),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("platform-image VM task input is invalid") from exc
        return result


@dataclass
class VmMediaCreationHandler:
    service: VmMediaCreationService

    def __call__(self, context: TaskContext, task: Task) -> str:
        task_input = VmMediaCreationTaskInput.decode(task.input_summary)
        if (
            task.task_type != "vm.create_from_media"
            or task.host_id != task_input.host_id
            or task.vm_uuid != task_input.vm_uuid
        ):
            raise ValueError("platform-image VM task scope does not match input")
        active_step: int | None = None

        def progress(sequence: int, percentage: float, message: str) -> None:
            nonlocal active_step
            if active_step is not None and active_step != sequence:
                context.finish_step(active_step)
            if active_step != sequence:
                context.start_step(sequence, message)
                active_step = sequence
            context.checkpoint(
                progress=percentage,
                current_step=sequence,
                message=message,
                checkpoint_data=task_input.encode(),
            )

        try:
            result = self.service.execute(
                task_input.plan_id,
                task_id=task.id,
                progress=progress,
                cancellation_requested=context.cancellation_requested,
            )
        except MediaCopyCancelled:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.CANCELLED)
            return "platform-image VM creation cancelled"
        except Exception:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.FAILED)
            raise
        if active_step is not None:
            context.finish_step(active_step)
        return result
