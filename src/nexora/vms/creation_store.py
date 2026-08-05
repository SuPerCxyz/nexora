"""Transaction-scoped VM creation plan state changes."""

from datetime import UTC, datetime

from nexora.db import Database
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.creation_models import VmCreationPlan


class VmCreationPlanStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load_for_execution(self, plan_id: str) -> VmCreationPlan:
        with self.database.session() as session:
            plan = session.get(VmCreationPlan, plan_id)
            if plan is None or plan.status not in {
                VmChangePlanStatus.CONFIRMED,
                VmChangePlanStatus.RUNNING,
            }:
                raise ValueError("VM creation plan cannot be executed")
            return plan

    def mark_running(self, plan_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmCreationPlan, plan_id)
            if plan is None or plan.status not in {
                VmChangePlanStatus.CONFIRMED,
                VmChangePlanStatus.RUNNING,
            }:
                raise ValueError("VM creation plan state changed before execution")
            plan.status = VmChangePlanStatus.RUNNING

    def mark_succeeded(self, plan_id: str, resource_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmCreationPlan, plan_id)
            if plan is not None:
                plan.status = VmChangePlanStatus.SUCCEEDED
                plan.result_resource_id = resource_id
                plan.finished_at = datetime.now(UTC)

    def mark_failed(self, plan_id: str, error: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmCreationPlan, plan_id)
            if plan is not None:
                plan.status = VmChangePlanStatus.FAILED
                plan.finished_at = datetime.now(UTC)
                plan.error_message = error[:2_048]
