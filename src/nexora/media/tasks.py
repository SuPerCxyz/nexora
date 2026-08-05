"""Persistent media library scan task handler."""

from dataclasses import dataclass

from nexora.media.scanner import MediaScanCancelled, MediaScanner
from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus


@dataclass
class MediaScanHandler:
    scanner: MediaScanner

    def __call__(self, context: TaskContext, task: Task) -> str:
        if task.host_id is not None or task.vm_uuid is not None:
            raise ValueError("media scan task must be platform scoped")
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
            )

        try:
            summary = self.scanner.scan(
                progress=progress,
                cancellation_requested=context.cancellation_requested,
            )
        except MediaScanCancelled:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.CANCELLED)
            return "media scan cancelled"
        except Exception:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.FAILED)
            raise
        if active_step is not None:
            context.finish_step(active_step)
        return summary
