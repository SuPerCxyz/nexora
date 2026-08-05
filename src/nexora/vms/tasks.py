"""Persistent VM operation task handlers."""

from dataclasses import dataclass

from nexora.tasks.coordinator import TaskContext
from nexora.tasks.models import Task, TaskStepStatus
from nexora.vms.contracts import LifecycleTaskInput, VmChangeTaskInput
from nexora.vms.cpu_changes import VmCpuChangeService
from nexora.vms.lifecycle import DomainLifecycleService, LifecycleCancelled


@dataclass
class VmLifecycleHandler:
    service: DomainLifecycleService

    def __call__(self, context: TaskContext, task: Task) -> str:
        task_input = LifecycleTaskInput.decode(task.input_summary)
        if task.host_id != task_input.base.host_id or task.vm_uuid != task_input.base.native_id:
            raise ValueError("VM lifecycle task scope does not match input")
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
                task_input,
                task_id=task.id,
                progress=progress,
                cancellation_requested=context.cancellation_requested,
            )
        except LifecycleCancelled:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.CANCELLED)
            return "VM lifecycle task cancelled"
        except Exception:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.FAILED)
            raise
        if active_step is not None:
            context.finish_step(active_step)
        return summary


@dataclass
class VmCpuChangeHandler:
    service: VmCpuChangeService

    def __call__(self, context: TaskContext, task: Task) -> str:
        task_input = VmChangeTaskInput.decode(task.input_summary)
        if task.host_id != task_input.host_id or task.vm_uuid != task_input.vm_uuid:
            raise ValueError("VM CPU task scope does not match input")
        expected_task_type = {
            "cpu_topology": "vm.cpu_change",
            "memory_config": "vm.memory_change",
            "disk_attach": "vm.disk_change",
            "disk_detach": "vm.disk_change",
            "interface_attach": "vm.network_change",
            "interface_detach": "vm.network_change",
            "interface_update": "vm.network_change",
            "cdrom_mount": "vm.cdrom_change",
            "cdrom_eject": "vm.cdrom_change",
            "cdrom_platform_mount": "vm.platform_iso_change",
            "cdrom_platform_eject": "vm.platform_iso_change",
            "cdrom_cache_mount": "vm.cached_iso_change",
            "cdrom_cache_eject": "vm.cached_iso_change",
            "numa_config": "vm.advanced_change",
            "cputune_config": "vm.advanced_change",
            "advanced_devices": "vm.advanced_change",
            "host_device_attach": "vm.advanced_change",
            "host_device_detach": "vm.advanced_change",
            "shared_directory_attach": "vm.advanced_change",
            "shared_directory_detach": "vm.advanced_change",
        }.get(task_input.change_type)
        if task.task_type != expected_task_type:
            raise ValueError("VM change task type does not match input")
        active_step: int | None = None

        def progress(sequence: int, message: str) -> None:
            nonlocal active_step
            if active_step is not None:
                context.finish_step(active_step)
            context.start_step(sequence, message)
            active_step = sequence
            context.checkpoint(
                progress=(sequence - 1) / max(1, task.total_steps) * 100,
                current_step=sequence,
                message=message,
            )

        try:
            summary = self.service.execute(
                task_input.plan_id,
                task_id=task.id,
                expected_change_type=task_input.change_type,
                progress=progress,
            )
        except Exception:
            if active_step is not None:
                context.finish_step(active_step, TaskStepStatus.FAILED)
            raise
        if active_step is not None:
            context.finish_step(active_step)
        return summary


@dataclass
class VmAdvancedChangeHandler:
    services: dict[str, VmCpuChangeService]

    def __call__(self, context: TaskContext, task: Task) -> str:
        task_input = VmChangeTaskInput.decode(task.input_summary)
        if task.task_type != "vm.advanced_change":
            raise ValueError("VM advanced task type does not match input")
        service = self.services.get(task_input.change_type)
        if service is None:
            raise ValueError("VM advanced change type is unsupported")
        return VmCpuChangeHandler(service)(context, task)
