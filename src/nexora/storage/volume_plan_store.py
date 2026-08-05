"""Transaction-scoped storage volume plan state changes."""

from datetime import UTC, datetime

from nexora.db import Database
from nexora.storage.models import StoragePoolPlanStatus
from nexora.storage.volume_models import StorageVolumeChangePlan


class StorageVolumePlanStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load_for_execution(self, plan_id: str) -> StorageVolumeChangePlan:
        with self.database.session() as session:
            plan = session.get(StorageVolumeChangePlan, plan_id)
            if plan is None or plan.status not in {
                StoragePoolPlanStatus.CONFIRMED,
                StoragePoolPlanStatus.RUNNING,
            }:
                raise ValueError("storage volume plan cannot be executed")
            return plan

    def mark_running(self, plan_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(StorageVolumeChangePlan, plan_id)
            if plan is None or plan.status not in {
                StoragePoolPlanStatus.CONFIRMED,
                StoragePoolPlanStatus.RUNNING,
            }:
                raise ValueError("storage volume plan state changed before execution")
            plan.status = StoragePoolPlanStatus.RUNNING

    def mark_succeeded(
        self,
        plan_id: str,
        resource_id: str,
        native_id: str,
    ) -> None:
        with self.database.session() as session:
            plan = session.get(StorageVolumeChangePlan, plan_id)
            if plan is not None:
                plan.volume_resource_id = resource_id
                plan.volume_native_id = native_id
                plan.status = StoragePoolPlanStatus.SUCCEEDED
                plan.finished_at = datetime.now(UTC)

    def mark_failed(self, plan_id: str, error: str) -> None:
        with self.database.session() as session:
            plan = session.get(StorageVolumeChangePlan, plan_id)
            if plan is not None:
                plan.status = StoragePoolPlanStatus.FAILED
                plan.finished_at = datetime.now(UTC)
                plan.error_message = error[:2_048]
