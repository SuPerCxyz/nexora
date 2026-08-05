"""Persistent blank-disk VM creation task contract and handler."""

import json
from dataclasses import dataclass
from uuid import UUID

from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus
from nexora.vms.blank_creation_service import VmBlankCreationService


@dataclass(frozen=True)
class VmBlankCreationTaskInput:
    plan_id: str
    host_id: str
    vm_uuid: str

    def encode(self) -> str:
        return json.dumps(vars(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str | None) -> "VmBlankCreationTaskInput":
        if value is None or len(value) > 1_024:
            raise ValueError("blank-disk VM task input is unavailable")
        try:
            payload = json.loads(value)
            result = cls(
                str(payload["plan_id"]),
                str(payload["host_id"]),
                str(UUID(str(payload["vm_uuid"]))),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("blank-disk VM task input is invalid") from exc
        if not result.plan_id or not result.host_id:
            raise ValueError("blank-disk VM task input is invalid")
        return result


@dataclass
class VmBlankCreationHandler:
    service: VmBlankCreationService

    def __call__(self, context: TaskContext, task: Task) -> str:
        task_input = VmBlankCreationTaskInput.decode(task.input_summary)
        if (
            task.task_type != "vm.create_blank"
            or task.host_id != task_input.host_id
            or task.vm_uuid != task_input.vm_uuid
        ):
            raise ValueError("blank-disk VM task scope does not match input")
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
