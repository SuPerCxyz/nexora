"""Persistent task contract and handler for shutdown full cloning."""

import json
from dataclasses import dataclass
from uuid import UUID

from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus
from nexora.vms.clone_service import VmCloneService


@dataclass(frozen=True)
class VmCloneTaskInput:
    plan_id: str
    source_host_id: str
    source_vm_uuid: str
    target_host_id: str
    target_vm_uuid: str

    def encode(self) -> str:
        return json.dumps(vars(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str | None) -> "VmCloneTaskInput":
        if value is None or len(value) > 2_048:
            raise ValueError("VM clone task input is unavailable")
        try:
            payload = json.loads(value)
            result = cls(
                str(payload["plan_id"]),
                str(payload["source_host_id"]),
                str(UUID(str(payload["source_vm_uuid"]))),
                str(payload["target_host_id"]),
                str(UUID(str(payload["target_vm_uuid"]))),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("VM clone task input is invalid") from exc
        return result


@dataclass
class VmCloneHandler:
    service: VmCloneService

    def __call__(self, context: TaskContext, task: Task) -> str:
        task_input = VmCloneTaskInput.decode(task.input_summary)
        if (
            task.task_type != "vm.clone"
            or task.host_id != task_input.source_host_id
            or task.vm_uuid != task_input.source_vm_uuid
        ):
            raise ValueError("VM clone task scope does not match input")
        active_step: int | None = None

        def progress(
            sequence: int,
            percentage: float,
            message: str,
            checkpoint: str | None,
        ) -> None:
            nonlocal active_step
            if active_step != sequence:
                if active_step is not None:
                    context.finish_step(active_step)
                context.start_step(sequence, message)
                active_step = sequence
            context.checkpoint(
                progress=percentage,
                current_step=sequence,
                message=message,
                checkpoint_data=checkpoint,
            )

        try:
            summary = self.service.execute(
                task_input.plan_id,
                task_id=task.id,
                progress=progress,
                cancellation_requested=context.cancellation_requested,
            )
        except Exception:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.FAILED)
            raise
        if active_step is not None:
            context.finish_step(active_step)
        return summary
