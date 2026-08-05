"""Persistent task handlers for managed host operations."""

from dataclasses import dataclass

from nexora.hosts.probe import HostProbeService
from nexora.tasks.coordinator import TaskContext
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.models import Task, TaskStepStatus


@dataclass
class HostCapabilityProbeHandler:
    probe: HostProbeService

    def __call__(self, context: TaskContext, task: Task) -> str:
        if task.host_id is None:
            raise ValueError("host capability task has no host")
        active_step: int | None = None

        def progress(sequence: int, total: int, name: str) -> None:
            nonlocal active_step
            if active_step is not None:
                context.finish_step(active_step)
            context.start_step(sequence, name)
            active_step = sequence
            context.checkpoint(
                progress=(sequence - 1) / total * 100,
                current_step=sequence,
                message=name,
            )

        try:
            report = self.probe.run(task.host_id, progress=progress)
        except Exception:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.FAILED)
            raise
        if active_step is not None:
            context.finish_step(active_step)
        context.checkpoint(
            progress=100,
            current_step=task.total_steps,
            message="Capability probe complete",
        )
        context.queue.enqueue(
            TaskCreate(
                task_type="host.resource_discovery",
                title="发现节点已有资源",
                idempotency_scope=f"host:{task.host_id}:resource-discovery",
                idempotency_key=task.id,
                host_id=task.host_id,
                total_steps=6,
                resumable=False,
                recovery_strategy="verify_only",
            )
        )
        return f"healthy={report.healthy}; observations={len(report.observations)}"
