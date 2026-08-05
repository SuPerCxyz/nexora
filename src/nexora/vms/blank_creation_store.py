"""Transaction-scoped blank-disk VM creation plan state changes."""

from datetime import UTC, datetime

from nexora.db import Database
from nexora.vms.blank_creation_models import VmBlankCreationPlan
from nexora.vms.change_models import VmChangePlanStatus


class VmBlankCreationPlanStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load_for_execution(self, plan_id: str) -> VmBlankCreationPlan:
        with self.database.session() as session:
            plan = session.get(VmBlankCreationPlan, plan_id)
            if plan is None or plan.status not in {
                VmChangePlanStatus.CONFIRMED,
                VmChangePlanStatus.RUNNING,
            }:
                raise ValueError("blank-disk VM plan cannot be executed")
            return plan

    def mark_running(self, plan_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmBlankCreationPlan, plan_id)
            if plan is None or plan.status not in {
                VmChangePlanStatus.CONFIRMED,
                VmChangePlanStatus.RUNNING,
            }:
                raise ValueError("blank-disk VM plan state changed")
            plan.status = VmChangePlanStatus.RUNNING

    def mark_succeeded(self, plan_id: str, resource_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmBlankCreationPlan, plan_id)
            if plan is not None:
                plan.status = VmChangePlanStatus.SUCCEEDED
                plan.result_resource_id = resource_id
                plan.finished_at = datetime.now(UTC)

    def mark_failed(self, plan_id: str, error: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmBlankCreationPlan, plan_id)
            if plan is not None:
                plan.status = VmChangePlanStatus.FAILED
                plan.error_message = error[:2_048]
                plan.finished_at = datetime.now(UTC)
