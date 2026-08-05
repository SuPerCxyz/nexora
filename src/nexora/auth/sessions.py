"""Opaque administrator session management."""

import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from nexora.auth.models import Administrator, AdminSession
from nexora.auth.tokens import digest_token
from nexora.db import Database


@dataclass(frozen=True)
class SessionCredentials:
    token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class SessionIdentity:
    administrator_id: int
    username: str
    token_hash: str
    session_timeout_minutes: int
    global_monospace: bool
    density: str
    language: str
    timezone: str


class SessionService:
    """Create, validate, and revoke server-side sessions."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, administrator_id: int) -> SessionCredentials:
        now = datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        with self.database.session() as session:
            administrator = session.get(Administrator, administrator_id)
            if administrator is None:
                raise LookupError("administrator does not exist")
            expires_at = now + timedelta(minutes=administrator.session_timeout_minutes)
            session.add(
                AdminSession(
                    token_hash=digest_token(token),
                    administrator_id=administrator.id,
                    session_version=administrator.session_version,
                    csrf_token_hash=digest_token(csrf_token),
                    created_at=now,
                    last_seen_at=now,
                    expires_at=expires_at,
                )
            )
        return SessionCredentials(token=token, csrf_token=csrf_token, expires_at=expires_at)

    def resolve(self, token: str | None) -> SessionIdentity | None:
        if not token:
            return None
        now = datetime.now(UTC)
        statement = (
            select(AdminSession, Administrator)
            .join(Administrator, Administrator.id == AdminSession.administrator_id)
            .where(
                AdminSession.token_hash == digest_token(token),
                AdminSession.revoked_at.is_(None),
                AdminSession.expires_at > now,
                AdminSession.session_version == Administrator.session_version,
            )
        )
        with self.database.session() as session:
            row = session.execute(statement).one_or_none()
            if row is None:
                return None
            stored_session, administrator = row
            stored_session.last_seen_at = now
            return SessionIdentity(
                administrator.id,
                administrator.username,
                stored_session.token_hash,
                administrator.session_timeout_minutes,
                administrator.global_monospace,
                administrator.density,
                administrator.language,
                administrator.timezone,
            )

    def verify_csrf(self, token: str, csrf_token: str | None) -> bool:
        if not csrf_token:
            return False
        now = datetime.now(UTC)
        statement = (
            select(AdminSession.csrf_token_hash)
            .join(Administrator, Administrator.id == AdminSession.administrator_id)
            .where(
                AdminSession.token_hash == digest_token(token),
                AdminSession.revoked_at.is_(None),
                AdminSession.expires_at > now,
                AdminSession.session_version == Administrator.session_version,
            )
        )
        with self.database.session() as session:
            stored_hash = session.execute(statement).scalar_one_or_none()
            return stored_hash is not None and hmac.compare_digest(
                stored_hash, digest_token(csrf_token)
            )

    def revoke(self, token: str) -> None:
        statement = (
            update(AdminSession)
            .where(AdminSession.token_hash == digest_token(token))
            .values(revoked_at=datetime.now(UTC))
        )
        with self.database.session() as session:
            session.execute(statement)
