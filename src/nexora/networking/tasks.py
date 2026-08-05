"""Task handler for network change operations."""

from nexora.networking.write_service import NetworkWriteService
from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task


class NetworkChangeHandler:
    def __init__(self, service: NetworkWriteService) -> None:
        self.service = service

    def __call__(self, context: TaskContext, task: Task) -> str:
        summary = task.input_summary or ""
        parts = summary.split(":", 2)
        if len(parts) != 3:
            raise ValueError("network change task input is invalid")
        plan_id, host_id, _change_type = parts
        if task.host_id != host_id:
            raise ValueError("network change task scope does not match")
        context.start_step(1, "Execute network change")
        result = self.service.execute(plan_id, host_id=host_id)
        context.finish_step(1)
        context.start_step(2, "Verify")
        context.finish_step(2)
        return result
