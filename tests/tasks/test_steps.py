from collections.abc import Iterator

import pytest

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.tasks.models import TaskStep, TaskStepStatus
from nexora.tasks.queue import TaskCreate, TaskQueue
from nexora.tasks.steps import TaskStepStore


@pytest.fixture
def task_steps(settings: Settings) -> Iterator[tuple[TaskQueue, TaskStepStore]]:
    database = Database(settings)
    upgrade_database(database)
    try:
        yield TaskQueue(database), TaskStepStore(database)
    finally:
        database.dispose()


def _claimed_task(queue: TaskQueue) -> str:
    task = queue.enqueue(
        TaskCreate(
            task_type="test",
            title="Step test",
            idempotency_scope="test",
            idempotency_key="step",
            total_steps=2,
        )
    )
    assert queue.claim_next("worker-1") is not None
    return task.id


def test_step_lifecycle_is_durable(
    task_steps: tuple[TaskQueue, TaskStepStore],
) -> None:
    queue, steps = task_steps
    task_id = _claimed_task(queue)

    assert steps.start(task_id, "worker-1", sequence=1, name="Inspect")
    assert steps.finish(
        task_id,
        "worker-1",
        sequence=1,
        status=TaskStepStatus.SUCCEEDED,
        checkpoint_data='{"done":true}',
    )

    with queue.database.session() as session:
        step = session.get(TaskStep, 1)
        assert step is not None
        assert TaskStepStatus.SUCCEEDED == step.status
        assert '{"done":true}' == step.checkpoint_data


def test_step_requires_current_lease_owner(
    task_steps: tuple[TaskQueue, TaskStepStore],
) -> None:
    queue, steps = task_steps
    task_id = _claimed_task(queue)

    assert steps.start(task_id, "worker-2", sequence=1, name="Inspect") is False
    assert (
        steps.finish(
            task_id,
            "worker-2",
            sequence=1,
            status=TaskStepStatus.FAILED,
        )
        is False
    )


def test_step_cannot_exceed_declared_total(
    task_steps: tuple[TaskQueue, TaskStepStore],
) -> None:
    queue, steps = task_steps
    task_id = _claimed_task(queue)

    with pytest.raises(ValueError, match="exceeds total"):
        steps.start(task_id, "worker-1", sequence=3, name="Invalid")
