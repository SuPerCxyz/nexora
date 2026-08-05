"""Persistent VM delete and rename task handler."""

import json
from dataclasses import dataclass
from uuid import UUID

from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus
from nexora.vms.remove_service import VmRemoveService


@dataclass(frozen=True)
class VmRemoveTaskInput:
    plan_id: str
    host_id: str
    vm_uuid: str

    def encode(self) -> str:
        return json.dumps(vars(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str | None) -> "VmRemoveTaskInput":
        if value is None or len(value) > 1_024:
            raise ValueError("VM remove task input is unavailable")
        try:
            payload = json.loads(value)
            result = cls(
                str(payload["plan_id"]),
                str(payload["host_id"]),
                str(UUID(str(payload["vm_uuid"]))),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("VM remove task input is invalid") from exc
        if not result.plan_id or not result.host_id:
            raise ValueError("VM remove task input is invalid")
        return result


@dataclass
class VmRemoveHandler:
    service: VmRemoveService

    def __call__(self, context: TaskContext, task: Task) -> str:
        task_input = VmRemoveTaskInput.decode(task.input_summary)
        if (
            task.task_type != "vm.remove"
            or task.host_id != task_input.host_id
            or task.vm_uuid != task_input.vm_uuid
        ):
            raise ValueError("VM remove task scope does not match input")
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
