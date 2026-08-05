"""State transitions for persistent Snapshot change plans."""

from datetime import UTC, datetime

from nexora.db import Database
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.snapshot_models import SnapshotChangePlan


class SnapshotPlanStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load_confirmed(self, plan_id: str) -> SnapshotChangePlan:
        with self.database.session() as session:
            plan = session.get(SnapshotChangePlan, plan_id)
            if plan is None or plan.status != VmChangePlanStatus.CONFIRMED:
                raise ValueError("Snapshot plan is not confirmed")
            session.expunge(plan)
            return plan

    def mark_running(self, plan_id: str) -> None:
        self._update(plan_id, VmChangePlanStatus.RUNNING)

    def mark_succeeded(self, plan_id: str) -> None:
        self._update(plan_id, VmChangePlanStatus.SUCCEEDED, finished=True)

    def mark_failed(self, plan_id: str, message: str) -> None:
        self._update(
            plan_id,
            VmChangePlanStatus.FAILED,
            error_message=message[:4_096],
            finished=True,
        )

    def _update(
        self,
        plan_id: str,
        status: str,
        *,
        error_message: str | None = None,
        finished: bool = False,
    ) -> None:
        with self.database.session() as session:
            plan = session.get(SnapshotChangePlan, plan_id)
            if plan is None:
                raise ValueError("Snapshot plan is unavailable")
            plan.status = status
            plan.error_message = error_message
            if finished:
                plan.finished_at = datetime.now(UTC)
