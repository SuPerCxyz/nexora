"""Atomic creation, claim, expiry, and recovery of console sessions."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.engine import CursorResult

from nexora.auth.tokens import digest_token
from nexora.consoles.models import ConsoleKind, ConsoleSession, ConsoleStatus
from nexora.db import Database

PENDING_TTL = timedelta(seconds=60)


@dataclass(frozen=True)
class ConsoleCredentials:
    session_id: str
    token: str
    expires_at: datetime


class ConsoleSessionStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        administrator_session_hash: str,
        host_id: str,
        vm_uuid: str,
        kind: ConsoleKind,
        *,
        now: datetime | None = None,
    ) -> ConsoleCredentials:
        created = now or datetime.now(UTC)
        canonical_uuid = str(UUID(vm_uuid))
        token = secrets.token_urlsafe(32)
        session_id = str(uuid4())
        expires_at = created + PENDING_TTL
        with self.database.session() as session:
            session.add(
                ConsoleSession(
                    id=session_id,
                    token_digest=digest_token(token),
                    administrator_session_hash=administrator_session_hash,
                    host_id=host_id,
                    vm_uuid=canonical_uuid,
                    kind=kind,
                    status=ConsoleStatus.PENDING,
                    created_at=created,
                    expires_at=expires_at,
                )
            )
        return ConsoleCredentials(session_id, token, expires_at)

    def claim(
        self,
        session_id: str,
        token: str,
        administrator_session_hash: str,
        *,
        now: datetime | None = None,
    ) -> ConsoleSession | None:
        claimed = now or datetime.now(UTC)
        statement = (
            update(ConsoleSession)
            .where(
                ConsoleSession.id == session_id,
                ConsoleSession.token_digest == digest_token(token),
                ConsoleSession.administrator_session_hash == administrator_session_hash,
                ConsoleSession.status == ConsoleStatus.PENDING,
                ConsoleSession.expires_at > claimed,
            )
            .values(
                status=ConsoleStatus.ACTIVE,
                claimed_at=claimed,
                last_activity_at=claimed,
            )
        )
        with self.database.session() as session:
            if _rowcount(session.execute(statement)) != 1:
                return None
            stored = session.get(ConsoleSession, session_id)
            if stored is None:
                return None
            session.expunge(stored)
            return stored

    def close(
        self,
        session_id: str,
        *,
        status: ConsoleStatus = ConsoleStatus.CLOSED,
        now: datetime | None = None,
    ) -> None:
        closed = now or datetime.now(UTC)
        with self.database.session() as session:
            session.execute(
                update(ConsoleSession)
                .where(
                    ConsoleSession.id == session_id,
                    ConsoleSession.status.in_((ConsoleStatus.PENDING, ConsoleStatus.ACTIVE)),
                )
                .values(status=status, closed_at=closed)
            )

    def recover(self, *, now: datetime | None = None) -> tuple[int, int]:
        recovered = now or datetime.now(UTC)
        with self.database.session() as session:
            interrupted = _rowcount(
                session.execute(
                    update(ConsoleSession)
                    .where(ConsoleSession.status == ConsoleStatus.ACTIVE)
                    .values(status=ConsoleStatus.INTERRUPTED, closed_at=recovered)
                )
            )
            expired = _rowcount(
                session.execute(
                    update(ConsoleSession)
                    .where(
                        ConsoleSession.status == ConsoleStatus.PENDING,
                        ConsoleSession.expires_at <= recovered,
                    )
                    .values(status=ConsoleStatus.EXPIRED, closed_at=recovered)
                )
            )
        return interrupted, expired


def _rowcount(result: object) -> int:
    return cast(CursorResult[Any], result).rowcount
