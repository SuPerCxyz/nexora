from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.tasks.models import TaskStatus
from nexora.tasks.queue import TaskCreate, TaskQueue


@pytest.fixture
def task_queue(settings: Settings) -> Iterator[TaskQueue]:
    database = Database(settings)
    upgrade_database(database)
    try:
        yield TaskQueue(database)
    finally:
        database.dispose()


def _create(key: str = "request-1") -> TaskCreate:
    return TaskCreate(
        task_type="test",
        title="Test task",
        idempotency_scope="host:host-1",
        idempotency_key=key,
        total_steps=2,
        resumable=True,
        recovery_strategy="verify_only",
    )


def test_enqueue_is_idempotent(task_queue: TaskQueue) -> None:
    first = task_queue.enqueue(_create())
    second = task_queue.enqueue(_create())

    assert first.id == second.id
    assert first.operation_id == second.operation_id


def test_only_one_worker_can_claim_a_task(task_queue: TaskQueue) -> None:
    queued = task_queue.enqueue(_create())

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(
            executor.map(
                lambda owner: task_queue.claim_next(owner),
                ("worker-1", "worker-2"),
            )
        )

    claimed = [task for task in claims if task is not None]
    assert 1 == len(claimed)
    assert queued.id == claimed[0].id
    assert TaskStatus.RUNNING == claimed[0].status


def test_claim_can_be_scoped_to_registered_task_types(task_queue: TaskQueue) -> None:
    skipped = task_queue.enqueue(_create("skip"))
    selected = task_queue.enqueue(
        TaskCreate(
            task_type="supported",
            title="Supported",
            idempotency_scope="test",
            idempotency_key="supported",
        )
    )

    claimed = task_queue.claim_next("worker-1", task_types={"supported"})

    assert claimed is not None
    assert selected.id == claimed.id
    with task_queue.database.session() as session:
        stored = session.get(type(skipped), skipped.id)
        assert stored is not None
        assert TaskStatus.PENDING == stored.status


def test_heartbeat_checkpoint_and_finish_require_lease_owner(
    task_queue: TaskQueue,
) -> None:
    task = task_queue.enqueue(_create())
    claimed = task_queue.claim_next("worker-1")
    assert claimed is not None

    assert task_queue.heartbeat(task.id, "other-worker") is False
    assert task_queue.heartbeat(task.id, "worker-1") is True
    assert task_queue.checkpoint(task.id, "worker-1", progress=50, current_step=1)
    assert task_queue.finish(task.id, "worker-1", TaskStatus.SUCCEEDED)


def test_cancel_pending_and_running_tasks(task_queue: TaskQueue) -> None:
    pending = task_queue.enqueue(_create("pending"))
    assert task_queue.request_cancel(pending.id)

    running = task_queue.enqueue(_create("running"))
    assert task_queue.claim_next("worker-1") is not None
    assert task_queue.request_cancel(running.id)
    assert task_queue.finish(running.id, "worker-1", TaskStatus.CANCELLED)


def test_expired_lease_is_interrupted_not_replayed(task_queue: TaskQueue) -> None:
    task = task_queue.enqueue(_create())
    assert task_queue.claim_next("worker-1", lease_seconds=5) is not None

    recovered = task_queue.recover_stale(now=datetime.now(UTC) + timedelta(seconds=10))

    assert 1 == recovered
    assert task_queue.claim_next("worker-2") is None
    with task_queue.database.session() as session:
        stored = session.get(type(task), task.id)
        assert stored is not None
        assert TaskStatus.INTERRUPTED == stored.status


def test_shutdown_releases_only_owned_leases(task_queue: TaskQueue) -> None:
    first = task_queue.enqueue(_create("first"))
    second = task_queue.enqueue(_create("second"))
    assert task_queue.claim_next("worker-1") is not None
    assert task_queue.claim_next("worker-2") is not None

    interrupted = task_queue.interrupt_owned("worker-1", message="shutdown")

    assert 1 == interrupted
    with task_queue.database.session() as session:
        first_stored = session.get(type(first), first.id)
        second_stored = session.get(type(second), second.id)
        assert first_stored is not None
        assert second_stored is not None
        assert TaskStatus.INTERRUPTED == first_stored.status
        assert TaskStatus.RUNNING == second_stored.status


def test_startup_interrupts_previous_process_without_replay(task_queue: TaskQueue) -> None:
    task = task_queue.enqueue(_create("orphaned"))
    assert task_queue.claim_next("previous-process", lease_seconds=3_600) is not None

    recovered = task_queue.recover_orphaned_on_startup()

    assert 1 == recovered
    assert task_queue.claim_next("new-process") is None
    with task_queue.database.session() as session:
        stored = session.get(type(task), task.id)
        assert stored is not None
        assert TaskStatus.INTERRUPTED == stored.status
        assert "external state verification" in (stored.message or "")


def test_interrupted_retry_requires_explicit_recovery_request(task_queue: TaskQueue) -> None:
    task = task_queue.enqueue(
        TaskCreate(
            task_type="copy",
            title="Copy",
            idempotency_scope="copy",
            idempotency_key="recoverable",
            resumable=True,
            max_retries=1,
            recovery_strategy="retry_from_start",
        )
    )
    assert task_queue.claim_next("previous-process") is not None
    assert 1 == task_queue.recover_orphaned_on_startup()

    assert task_queue.request_recovery(task.id)
    recovered = task_queue.claim_next("new-process")
    assert recovered is not None
    assert 1 == recovered.retry_count
    assert not task_queue.request_recovery(task.id)
