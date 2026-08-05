"""Network change plan store with preview/confirm lifecycle."""

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from nexora.db import Database
from nexora.networking.models import NetworkChangePlan

PLAN_TTL = timedelta(minutes=10)
CONFIRMATION_WINDOW = timedelta(seconds=60)


class NetworkChangeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NetworkChangePreview:
    plan: NetworkChangePlan
    confirmation_token: str


class NetworkChangePlanStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        *,
        host_id: str,
        change_type: str,
        target_iface: str,
        change_input: dict[str, object],
        rollback_script: str,
    ) -> NetworkChangePreview:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        plan = NetworkChangePlan(
            id=str(uuid4()),
            host_id=host_id,
            change_type=change_type,
            target_iface=target_iface,
            change_input_json=json.dumps(change_input, sort_keys=True, separators=(",", ":")),
            rollback_script=rollback_script,
            confirmation_digest=hashlib.sha256(token.encode()).hexdigest(),
            status="preview",
            created_at=now,
            expires_at=now + PLAN_TTL,
        )
        with self.database.session() as session:
            session.add(plan)
        return NetworkChangePreview(plan, token)

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
    ) -> NetworkChangePlan:
        now = datetime.now(UTC)
        with self.database.session() as session:
            plan = session.get(NetworkChangePlan, plan_id)
            if plan is None or plan.status != "preview":
                raise NetworkChangeError("network change plan is unavailable")
            if plan.host_id != host_id:
                raise NetworkChangeError("network change plan scope does not match")
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                plan.status = "expired"
                raise NetworkChangeError("network change plan expired")
            submitted = hashlib.sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(submitted, plan.confirmation_digest):
                raise NetworkChangeError("network change confirmation is invalid")
            plan.status = "confirmed"
            plan.confirmed_at = now
            plan.confirmation_deadline = now + CONFIRMATION_WINDOW
            return plan

    def load_confirmed(self, plan_id: str) -> NetworkChangePlan:
        with self.database.session() as session:
            plan = session.get(NetworkChangePlan, plan_id)
            if plan is None or plan.status != "confirmed":
                raise NetworkChangeError("network change plan is not confirmed")
            session.expunge(plan)
            return plan

    def mark_running(self, plan_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(NetworkChangePlan, plan_id)
            if plan is not None:
                plan.status = "running"

    def mark_succeeded(self, plan_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(NetworkChangePlan, plan_id)
            if plan is not None:
                plan.status = "succeeded"

    def mark_failed(self, plan_id: str, message: str) -> None:
        with self.database.session() as session:
            plan = session.get(NetworkChangePlan, plan_id)
            if plan is not None:
                plan.status = "failed"

    def mark_rolled_back(self, plan_id: str) -> None:
        with self.database.session() as session:
            plan = session.get(NetworkChangePlan, plan_id)
            if plan is not None:
                plan.status = "rolled_back"
