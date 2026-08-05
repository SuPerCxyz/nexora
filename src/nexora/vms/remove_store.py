"""Transaction-scoped VM remove plan state changes."""

from datetime import UTC, datetime

from nexora.db import Database
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.remove_models import VmRemovePlan


class VmRemovePlanStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load_for_execution(self, plan_id: str) -> VmRemovePlan:
        with self.database.session() as session:
            plan = session.get(VmRemovePlan, plan_id)
            if plan is None or plan.status not in {
                VmChangePlanStatus.CONFIRMED,
                VmChangePlanStatus.RUNNING,
            }:
                raise ValueError("VM remove plan cannot be executed")
            return plan

    def mark_running(self, plan_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmRemovePlan, plan_id)
            if plan is None or plan.status not in {
                VmChangePlanStatus.CONFIRMED,
                VmChangePlanStatus.RUNNING,
            }:
                raise ValueError("VM remove plan state changed")
            plan.status = VmChangePlanStatus.RUNNING

    def mark_succeeded(self, plan_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmRemovePlan, plan_id)
            if plan is not None:
                plan.status = VmChangePlanStatus.SUCCEEDED
                plan.finished_at = datetime.now(UTC)

    def mark_failed(self, plan_id: str, error: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmRemovePlan, plan_id)
            if plan is not None:
                plan.status = VmChangePlanStatus.FAILED
                plan.error_message = error[:2_048]
                plan.finished_at = datetime.now(UTC)
