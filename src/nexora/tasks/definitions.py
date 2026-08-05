"""Task creation contracts and validated recovery strategies."""

from dataclasses import dataclass

RECOVERY_STRATEGIES = frozenset(
    {"verify_only", "resume_from_checkpoint", "rollback", "retry_from_start", "manual_intervention"}
)


@dataclass(frozen=True)
class TaskCreate:
    task_type: str
    title: str
    idempotency_scope: str
    idempotency_key: str
    host_id: str | None = None
    vm_uuid: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    total_steps: int = 0
    resumable: bool = False
    max_retries: int = 0
    recovery_strategy: str = "verify_only"
    input_summary: str | None = None
