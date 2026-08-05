from collections.abc import Iterator

import pytest

from nexora.auth.models import Administrator
from nexora.auth.service import AuthService
from nexora.auth.sessions import SessionService
from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database


@pytest.fixture
def session_service(settings: Settings) -> Iterator[SessionService]:
    database = Database(settings)
    upgrade_database(database)
    AuthService(database).initialize("admin", "a-valid-password", "a-valid-password")
    try:
        yield SessionService(database)
    finally:
        database.dispose()


def test_session_is_opaque_and_resolvable(session_service: SessionService) -> None:
    credentials = session_service.create(1)

    identity = session_service.resolve(credentials.token)

    assert identity is not None
    assert 1 == identity.administrator_id
    assert "admin" == identity.username
    assert credentials.token not in identity.token_hash
    assert session_service.verify_csrf(credentials.token, credentials.csrf_token) is True
    assert session_service.verify_csrf(credentials.token, "wrong-token") is False


def test_revoked_session_and_csrf_are_rejected(session_service: SessionService) -> None:
    credentials = session_service.create(1)

    session_service.revoke(credentials.token)

    assert session_service.resolve(credentials.token) is None
    assert session_service.verify_csrf(credentials.token, credentials.csrf_token) is False


def test_session_version_invalidates_existing_session(
    session_service: SessionService,
) -> None:
    credentials = session_service.create(1)
    with session_service.database.session() as session:
        administrator = session.get(Administrator, 1)
        assert administrator is not None
        administrator.session_version += 1

    assert session_service.resolve(credentials.token) is None
    assert session_service.verify_csrf(credentials.token, credentials.csrf_token) is False
