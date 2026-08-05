"""Transaction-scoped shutdown clone plan state changes."""

from datetime import UTC, datetime

from nexora.db import Database
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.clone_models import VmClonePlan


class VmClonePlanStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load_for_execution(self, plan_id: str) -> VmClonePlan:
        with self.database.session() as session:
            plan = session.get(VmClonePlan, plan_id)
            if plan is None or plan.status not in {
                VmChangePlanStatus.CONFIRMED,
                VmChangePlanStatus.RUNNING,
            }:
                raise ValueError("VM clone plan cannot be executed")
            session.expunge(plan)
            return plan

    def mark_running(self, plan_id: str) -> None:
        self._status(plan_id, VmChangePlanStatus.RUNNING)

    def mark_succeeded(self, plan_id: str, resource_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmClonePlan, plan_id)
            if plan is not None:
                plan.status = VmChangePlanStatus.SUCCEEDED
                plan.result_resource_id = resource_id
                plan.finished_at = datetime.now(UTC)

    def mark_failed(self, plan_id: str, error: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmClonePlan, plan_id)
            if plan is not None:
                plan.status = VmChangePlanStatus.FAILED
                plan.error_message = error[:2_048]
                plan.finished_at = datetime.now(UTC)

    def _status(self, plan_id: str, status: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmClonePlan, plan_id)
            if plan is None:
                raise ValueError("VM clone plan is unavailable")
            plan.status = status
