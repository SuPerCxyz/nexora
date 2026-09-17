from collections.abc import Iterator

import pytest
from sqlalchemy import func, select

from nexora.auth.models import Administrator, LoginAttempt
from nexora.auth.service import (
    AlreadyInitializedError,
    AuthenticationFailedError,
    AuthService,
)
from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database


@pytest.fixture
def auth_service(settings: Settings) -> Iterator[AuthService]:
    database = Database(settings)
    upgrade_database(database)
    try:
        yield AuthService(database)
    finally:
        database.dispose()


def test_initialize_creates_one_hashed_administrator(auth_service: AuthService) -> None:
    administrator = auth_service.initialize(" admin ", "a-valid-password", "a-valid-password")

    assert "admin" == administrator.username
    assert administrator.password_hash.startswith("$argon2")
    assert auth_service.is_initialized() is True

    with pytest.raises(AlreadyInitializedError):
        auth_service.initialize("other", "a-valid-password", "a-valid-password")


def test_authenticate_records_success_and_failure(auth_service: AuthService) -> None:
    auth_service.initialize("admin", "a-valid-password", "a-valid-password")

    assert auth_service.authenticate("admin", "wrong-password", "127.0.0.1") is False
    assert auth_service.authenticate("admin", "a-valid-password", "127.0.0.1") is True

    with auth_service.database.session() as session:
        count = session.execute(select(func.count(LoginAttempt.id))).scalar_one()
        administrator = session.get(Administrator, 1)
        assert administrator is not None
        password_hash = administrator.password_hash

    assert 2 == count
    assert "a-valid-password" != password_hash


def test_update_account_changes_credentials_and_version(auth_service: AuthService) -> None:
    auth_service.initialize("admin", "a-valid-password", "a-valid-password")

    administrator = auth_service.update_account(
        current_password="a-valid-password",
        username="operator",
        new_password="newpass8",
        confirmation="newpass8",
    )

    assert "operator" == administrator.username
    assert 2 == administrator.session_version
    assert auth_service.authenticate("operator", "newpass8", "127.0.0.1") is True
    assert auth_service.authenticate("admin", "a-valid-password", "127.0.0.2") is False


def test_update_account_requires_current_password(auth_service: AuthService) -> None:
    auth_service.initialize("admin", "a-valid-password", "a-valid-password")

    with pytest.raises(AuthenticationFailedError):
        auth_service.update_account(
            current_password="wrong-password",
            username="operator",
        )
