"""Single-process persistent task coordinator."""

import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import Protocol
from uuid import uuid4

from nexora.tasks.locks import ResourceLockStore
from nexora.tasks.models import Task, TaskStatus, TaskStepStatus
from nexora.tasks.queue import TaskQueue
from nexora.tasks.steps import TaskStepStore

LOG = logging.getLogger(__name__)


class TaskHandler(Protocol):
    def __call__(self, context: "TaskContext", task: Task) -> str | None: ...


@dataclass(frozen=True)
class TaskContext:
    """Safe handler access to durable progress and cancellation."""

    queue: TaskQueue
    task_id: str
    owner: str

    @property
    def steps(self) -> TaskStepStore:
        return TaskStepStore(self.queue.database)

    def checkpoint(
        self,
        *,
        progress: float,
        current_step: int,
        message: str | None = None,
        checkpoint_data: str | None = None,
    ) -> None:
        updated = self.queue.checkpoint(
            self.task_id,
            self.owner,
            progress=progress,
            current_step=current_step,
            message=message,
            checkpoint_data=checkpoint_data,
        )
        if not updated:
            raise RuntimeError("task lease was lost")

    def cancellation_requested(self) -> bool:
        return self.queue.cancellation_requested(self.task_id)

    def start_step(
        self,
        sequence: int,
        name: str,
        *,
        command_summary: str | None = None,
    ) -> None:
        if not self.steps.start(
            self.task_id,
            self.owner,
            sequence=sequence,
            name=name,
            command_summary=command_summary,
        ):
            raise RuntimeError("task lease was lost")

    def finish_step(
        self,
        sequence: int,
        status: TaskStepStatus = TaskStepStatus.SUCCEEDED,
        *,
        stdout_summary: str | None = None,
        stderr_summary: str | None = None,
        error_code: str | None = None,
        checkpoint_data: str | None = None,
    ) -> None:
        if not self.steps.finish(
            self.task_id,
            self.owner,
            sequence=sequence,
            status=status,
            stdout_summary=stdout_summary,
            stderr_summary=stderr_summary,
            error_code=error_code,
            checkpoint_data=checkpoint_data,
        ):
            raise RuntimeError("task step is not running or lease was lost")


class TaskCoordinator:
    """Claim durable tasks and execute registered handlers in a bounded pool."""

    def __init__(
        self,
        queue: TaskQueue,
        *,
        resource_locks: ResourceLockStore | None = None,
        concurrency: int = 4,
        poll_interval: float = 0.25,
        lease_seconds: int = 30,
    ) -> None:
        if not 1 <= concurrency <= 32:
            raise ValueError("invalid task concurrency")
        self.queue = queue
        self.resource_locks = resource_locks
        self.owner = f"coordinator-{uuid4()}"
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self.handlers: dict[str, TaskHandler] = {}
        self._stop = Event()
        self._thread: Thread | None = None
        self._pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="nexora-task")
        self._futures: dict[str, Future[None]] = {}
        self._lock = Lock()
        self._concurrency = concurrency

    def register(self, task_type: str, handler: TaskHandler) -> None:
        if self._thread is not None:
            raise RuntimeError("handlers must be registered before start")
        self.handlers[task_type] = handler

    def start(self) -> int:
        if self._thread is not None:
            raise RuntimeError("task coordinator already started")
        recovered = self.queue.recover_orphaned_on_startup()
        self._thread = Thread(target=self._run_loop, name="nexora-coordinator", daemon=True)
        self._thread.start()
        return recovered

    def stop(self, *, timeout: float = 10) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        deadline = time.monotonic() + timeout
        while self._has_running_futures() and time.monotonic() < deadline:
            self._collect_finished()
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        self.queue.interrupt_owned(
            self.owner,
            message="Application stopped before external state verification",
        )
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _has_running_futures(self) -> bool:
        with self._lock:
            return any(not future.done() for future in self._futures.values())

    def _run_loop(self) -> None:
        next_heartbeat = time.monotonic()
        while not self._stop.is_set():
            self._collect_finished()
            if time.monotonic() >= next_heartbeat:
                self._heartbeat_running()
                next_heartbeat = time.monotonic() + max(1, self.lease_seconds / 3)
            self._fill_capacity()
            self._stop.wait(self.poll_interval)

    def _collect_finished(self) -> None:
        with self._lock:
            finished = [task_id for task_id, future in self._futures.items() if future.done()]
            for task_id in finished:
                future = self._futures.pop(task_id)
                try:
                    future.result()
                except Exception:
                    LOG.error("task worker terminated unexpectedly: %s", task_id)

    def _heartbeat_running(self) -> None:
        with self._lock:
            task_ids = list(self._futures)
        for task_id in task_ids:
            heartbeat_ok = self.queue.heartbeat(
                task_id,
                self.owner,
                lease_seconds=self.lease_seconds,
            )
            if not heartbeat_ok:
                LOG.error("task lease heartbeat failed: %s", task_id)
            elif self.resource_locks is not None:
                self.resource_locks.renew_task(task_id)

    def _fill_capacity(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                if len(self._futures) >= self._concurrency:
                    return
            task = self.queue.claim_next(
                self.owner,
                lease_seconds=self.lease_seconds,
                task_types=self.handlers.keys(),
            )
            if task is None:
                return
            future = self._pool.submit(self._execute_task, task)
            with self._lock:
                self._futures[task.id] = future

    def _execute_task(self, task: Task) -> None:
        context = TaskContext(self.queue, task.id, self.owner)
        handler = self.handlers.get(task.task_type)
        if handler is None:
            self.queue.finish(
                task.id,
                self.owner,
                TaskStatus.FAILED,
                error_message="No handler is registered for this task type",
            )
            return
        try:
            if context.cancellation_requested():
                self.queue.finish(task.id, self.owner, TaskStatus.CANCELLED)
                return
            result = handler(context, task)
            terminal_status = (
                TaskStatus.CANCELLED if context.cancellation_requested() else TaskStatus.SUCCEEDED
            )
            self.queue.finish(
                task.id,
                self.owner,
                terminal_status,
                result_summary=result,
            )
        except Exception:
            LOG.error("task handler failed: id=%s type=%s", task.id, task.task_type)
            self.queue.finish(
                task.id,
                self.owner,
                TaskStatus.FAILED,
                error_message="Task handler failed",
            )
