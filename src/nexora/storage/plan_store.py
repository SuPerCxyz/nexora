"""Transaction-scoped storage pool plan state changes."""

from datetime import UTC, datetime

from nexora.db import Database
from nexora.storage.models import StoragePoolChangePlan, StoragePoolPlanStatus


class StoragePoolPlanStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load(
        self,
        plan_id: str,
        status: StoragePoolPlanStatus,
    ) -> StoragePoolChangePlan:
        with self.database.session() as session:
            plan = session.get(StoragePoolChangePlan, plan_id)
            if plan is None or plan.status != status:
                raise ValueError("storage pool plan has an invalid state")
            return plan

    def load_for_execution(self, plan_id: str) -> StoragePoolChangePlan:
        with self.database.session() as session:
            plan = session.get(StoragePoolChangePlan, plan_id)
            if plan is None or plan.status not in {
                StoragePoolPlanStatus.CONFIRMED,
                StoragePoolPlanStatus.RUNNING,
            }:
                raise ValueError("storage pool plan cannot be executed")
            return plan

    def mark_running(self, plan_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(StoragePoolChangePlan, plan_id)
            if plan is None or plan.status not in {
                StoragePoolPlanStatus.CONFIRMED,
                StoragePoolPlanStatus.RUNNING,
            }:
                raise ValueError("storage pool plan state changed before execution")
            plan.status = StoragePoolPlanStatus.RUNNING

    def mark_succeeded(self, plan_id: str, resource_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(StoragePoolChangePlan, plan_id)
            if plan is not None:
                plan.pool_resource_id = resource_id
                plan.status = StoragePoolPlanStatus.SUCCEEDED
                plan.finished_at = datetime.now(UTC)

    def mark_failed(self, plan_id: str, error: str) -> None:
        with self.database.session() as session:
            plan = session.get(StoragePoolChangePlan, plan_id)
            if plan is not None:
                plan.status = StoragePoolPlanStatus.FAILED
                plan.finished_at = datetime.now(UTC)
                plan.error_message = error[:2_048]
