"""Administrator initialization and authentication service."""

import re
from datetime import UTC, datetime

from sqlalchemy import select

from nexora.auth.models import Administrator, LoginAttempt
from nexora.auth.passwords import (
    hash_password,
    validate_password,
    verify_password,
)
from nexora.db import Database

ADMINISTRATOR_ID = 1
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
ALLOWED_DENSITIES = {"comfortable", "compact"}
ALLOWED_LANGUAGES = {"zh-CN", "en"}


class AlreadyInitializedError(RuntimeError):
    """Raised when a second administrator creation is attempted."""


class InvalidUsernameError(ValueError):
    """Raised when a username cannot be stored safely."""


class AuthenticationFailedError(RuntimeError):
    """Raised when the current password cannot authorize a change."""


class ConcurrentAccountChangeError(RuntimeError):
    """Raised when account state changed during password verification."""


class AuthService:
    """Coordinate single-administrator persistence and password checks."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def is_initialized(self) -> bool:
        """Return whether the single administrator exists."""

        with self.database.session() as session:
            return session.get(Administrator, ADMINISTRATOR_ID) is not None

    def initialize(
        self,
        username: str,
        password: str,
        confirmation: str,
    ) -> Administrator:
        """Atomically create the only administrator."""

        normalized = normalize_username(username)
        validate_password(password, confirmation)
        with self.database.session() as session:
            if session.get(Administrator, ADMINISTRATOR_ID) is not None:
                raise AlreadyInitializedError
            administrator = Administrator(
                id=ADMINISTRATOR_ID,
                username=normalized,
                password_hash=hash_password(password),
                session_version=1,
            )
            session.add(administrator)
        return administrator

    def authenticate(self, username: str, password: str, remote_address: str) -> bool:
        """Verify credentials and persist a bounded login-history event."""

        normalized = username.strip()
        now = datetime.now(UTC)
        with self.database.session() as session:
            administrator = session.get(Administrator, ADMINISTRATOR_ID)
            stored_hash = None
            if administrator is not None and administrator.username == normalized:
                stored_hash = administrator.password_hash

        succeeded = verify_password(password, stored_hash)
        with self.database.session() as session:
            session.add(
                LoginAttempt(
                    username=normalized[:64],
                    remote_address=remote_address[:64],
                    succeeded=succeeded,
                    occurred_at=now,
                )
            )
        return succeeded

    def update_account(
        self,
        *,
        current_password: str,
        username: str,
        new_password: str | None = None,
        confirmation: str | None = None,
        session_timeout_minutes: int = 30,
        global_monospace: bool = False,
        density: str = "comfortable",
        language: str = "zh-CN",
        timezone: str = "Asia/Shanghai",
    ) -> Administrator:
        """Update the username/password and invalidate all existing sessions."""

        normalized = normalize_username(username)
        if not 5 <= session_timeout_minutes <= 1_440:
            raise ValueError("Session 超时必须在 5 到 1440 分钟之间")
        if density not in ALLOWED_DENSITIES or language not in ALLOWED_LANGUAGES:
            raise ValueError("页面偏好设置无效")
        if not 1 <= len(timezone) <= 64:
            raise ValueError("时区设置无效")
        with self.database.session() as session:
            existing = session.get(Administrator, ADMINISTRATOR_ID)
            stored_hash = existing.password_hash if existing is not None else None
        if stored_hash is None or not verify_password(current_password, stored_hash):
            raise AuthenticationFailedError

        replacement_hash: str = stored_hash
        if new_password:
            validate_password(new_password, confirmation or "")
            replacement_hash = hash_password(new_password)

        with self.database.session() as session:
            administrator = session.get(Administrator, ADMINISTRATOR_ID)
            if administrator is None or administrator.password_hash != stored_hash:
                raise ConcurrentAccountChangeError
            administrator.username = normalized
            administrator.password_hash = replacement_hash
            administrator.session_version += 1
            administrator.session_timeout_minutes = session_timeout_minutes
            administrator.global_monospace = global_monospace
            administrator.density = density
            administrator.language = language
            administrator.timezone = timezone
        return administrator

    def login_history(self, *, limit: int = 20) -> list[LoginAttempt]:
        """Return the newest bounded login history."""

        statement = select(LoginAttempt).order_by(LoginAttempt.occurred_at.desc()).limit(limit)
        with self.database.session() as session:
            return list(session.scalars(statement))

def normalize_username(username: str) -> str:
    """Normalize and validate an administrator username."""

    normalized = username.strip()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise InvalidUsernameError
    return normalized
