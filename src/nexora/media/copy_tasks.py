"""Persistent remote media image copy task handler."""

from dataclasses import dataclass

from nexora.media.copy import MediaImageCopyService
from nexora.media.copy_contracts import MediaCopyInput
from nexora.media.copy_errors import MediaCopyCancelled
from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus


@dataclass
class MediaImageCopyHandler:
    service: MediaImageCopyService

    def __call__(self, context: TaskContext, task: Task) -> str:
        copy_input = MediaCopyInput.decode(task.input_summary)
        if task.host_id != copy_input.host_id or task.resource_id != copy_input.media_item_id:
            raise ValueError("media copy task scope does not match input")
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
                checkpoint_data=copy_input.encode(),
            )

        try:
            summary = self.service.execute(
                copy_input,
                task_id=task.id,
                progress=progress,
                cancellation_requested=context.cancellation_requested,
            )
        except MediaCopyCancelled:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.CANCELLED)
            return "media image copy cancelled"
        except Exception:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.FAILED)
            raise
        if active_step is not None:
            context.finish_step(active_step)
        return summary
