"""Persistent task adapter for VM Snapshot changes."""

from dataclasses import dataclass

from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus
from nexora.vms.contracts import VmChangeTaskInput
from nexora.vms.snapshot_delete_service import SnapshotDeleteService
from nexora.vms.snapshot_revert_service import SnapshotRevertService
from nexora.vms.snapshot_service import SnapshotService


@dataclass
class SnapshotChangeHandler:
    create_service: SnapshotService
    delete_service: SnapshotDeleteService
    revert_service: SnapshotRevertService

    def __call__(self, context: TaskContext, task: Task) -> str:
        task_input = VmChangeTaskInput.decode(task.input_summary)
        if (
            task.task_type != "vm.snapshot_change"
            or task_input.change_type
            not in {"snapshot_create", "snapshot_delete", "snapshot_revert"}
            or task.host_id != task_input.host_id
            or task.vm_uuid != task_input.vm_uuid
        ):
            raise ValueError("VM Snapshot task scope does not match input")
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
            if task_input.change_type == "snapshot_create":
                summary = self.create_service.execute_create(
                    task_input.plan_id,
                    task_id=task.id,
                    progress=progress,
                )
            elif task_input.change_type == "snapshot_delete":
                summary = self.delete_service.execute(
                    task_input.plan_id,
                    task_id=task.id,
                    progress=progress,
                )
            else:
                summary = self.revert_service.execute(
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
