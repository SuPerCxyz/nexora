"""Transaction-scoped state changes for persistent VM XML plans."""

from datetime import UTC, datetime

from nexora.db import Database
from nexora.vms.change_models import VmChangePlan, VmChangePlanStatus


class VmChangePlanStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load(self, plan_id: str, status: VmChangePlanStatus) -> VmChangePlan:
        with self.database.session() as session:
            plan = session.get(VmChangePlan, plan_id)
            if plan is None or plan.status != status:
                raise ValueError("VM change plan has an invalid state")
            return plan

    def mark_running(self, plan_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmChangePlan, plan_id)
            if plan is None or plan.status != VmChangePlanStatus.CONFIRMED:
                raise ValueError("VM change plan state changed before execution")
            plan.status = VmChangePlanStatus.RUNNING

    def mark_succeeded(self, plan_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmChangePlan, plan_id)
            if plan is not None:
                plan.status = VmChangePlanStatus.SUCCEEDED
                plan.finished_at = datetime.now(UTC)

    def mark_failed(self, plan_id: str, error: str) -> None:
        with self.database.session() as session:
            plan = session.get(VmChangePlan, plan_id)
            if plan is not None:
                plan.status = VmChangePlanStatus.FAILED
                plan.finished_at = datetime.now(UTC)
                plan.error_message = error[:2_048]
