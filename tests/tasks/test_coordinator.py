import time
from collections.abc import Iterator

import pytest

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.tasks.coordinator import TaskContext, TaskCoordinator
from nexora.tasks.models import Task, TaskStatus, TaskStep, TaskStepStatus
from nexora.tasks.queue import TaskCreate, TaskQueue


@pytest.fixture
def task_runtime(settings: Settings) -> Iterator[tuple[TaskQueue, TaskCoordinator]]:
    database = Database(settings)
    upgrade_database(database)
    queue = TaskQueue(database)
    coordinator = TaskCoordinator(queue, concurrency=2, poll_interval=0.01, lease_seconds=5)
    try:
        yield queue, coordinator
    finally:
        coordinator.stop()
        database.dispose()


def _task(queue: TaskQueue, key: str, task_type: str = "test") -> Task:
    return queue.enqueue(
        TaskCreate(
            task_type=task_type,
            title="Coordinator test",
            idempotency_scope="test",
            idempotency_key=key,
            total_steps=1,
        )
    )


def _wait_for_status(queue: TaskQueue, task_id: str, expected: TaskStatus) -> Task:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with queue.database.session() as session:
            task = session.get(Task, task_id)
            assert task is not None
            if task.status == expected:
                return task
        time.sleep(0.01)
    raise AssertionError(f"task did not reach {expected}")


def test_coordinator_executes_handler_and_checkpoint(
    task_runtime: tuple[TaskQueue, TaskCoordinator],
) -> None:
    queue, coordinator = task_runtime

    def handler(context: TaskContext, _task_value: Task) -> str:
        context.start_step(1, "Read remote state", command_summary="virsh list --all")
        context.checkpoint(progress=50, current_step=1, message="working")
        context.finish_step(1, stdout_summary="one domain")
        return "done"

    coordinator.register("test", handler)
    task = _task(queue, "success")
    coordinator.start()

    completed = _wait_for_status(queue, task.id, TaskStatus.SUCCEEDED)

    assert 100 == completed.progress
    assert "done" == completed.result_summary
    with queue.database.session() as session:
        step = session.get(TaskStep, 1)
        assert step is not None
        assert TaskStepStatus.SUCCEEDED == step.status
        assert 1 == step.attempt_count


def test_unregistered_task_is_not_claimed_or_modified(
    task_runtime: tuple[TaskQueue, TaskCoordinator],
) -> None:
    queue, coordinator = task_runtime
    task = _task(queue, "missing", task_type="missing")
    coordinator.start()
    time.sleep(0.05)

    with queue.database.session() as session:
        stored = session.get(Task, task.id)
        assert stored is not None
        assert TaskStatus.PENDING == stored.status


def test_running_handler_observes_cancellation(
    task_runtime: tuple[TaskQueue, TaskCoordinator],
) -> None:
    queue, coordinator = task_runtime

    def handler(context: TaskContext, _task_value: Task) -> None:
        deadline = time.monotonic() + 5
        while not context.cancellation_requested() and time.monotonic() < deadline:
            time.sleep(0.01)

    coordinator.register("test", handler)
    task = _task(queue, "cancel")
    coordinator.start()
    _wait_for_status(queue, task.id, TaskStatus.RUNNING)
    assert queue.request_cancel(task.id)

    _wait_for_status(queue, task.id, TaskStatus.CANCELLED)
