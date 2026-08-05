from datetime import UTC, datetime, timedelta

from nexora.config import Settings
from nexora.consoles.models import ConsoleKind, ConsoleSession, ConsoleStatus
from nexora.consoles.store import ConsoleSessionStore
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode

VM_UUID = "33333333-3333-3333-3333-333333333333"
ADMIN_SESSION = "a" * 64
NOW = datetime(2026, 7, 29, 7, 0, tzinfo=UTC)


def test_console_token_is_digest_only_and_claim_is_single_use(settings: Settings) -> None:
    database = _database(settings)
    store = ConsoleSessionStore(database)
    credentials = store.create(
        ADMIN_SESSION,
        "host-1",
        VM_UUID,
        ConsoleKind.SERIAL,
        now=NOW,
    )
    with database.session() as session:
        stored = session.get(ConsoleSession, credentials.session_id)
        assert stored is not None
        assert credentials.token != stored.token_digest
        assert 64 == len(stored.token_digest)

    claimed = store.claim(
        credentials.session_id,
        credentials.token,
        ADMIN_SESSION,
        now=NOW + timedelta(seconds=1),
    )
    assert claimed is not None
    assert ConsoleStatus.ACTIVE == claimed.status
    assert (
        store.claim(
            credentials.session_id,
            credentials.token,
            ADMIN_SESSION,
            now=NOW + timedelta(seconds=2),
        )
        is None
    )
    database.dispose()


def test_console_claim_binds_session_and_expiry(settings: Settings) -> None:
    database = _database(settings)
    store = ConsoleSessionStore(database)
    credentials = store.create(
        ADMIN_SESSION,
        "host-1",
        VM_UUID,
        ConsoleKind.SERIAL,
        now=NOW,
    )
    assert store.claim(credentials.session_id, credentials.token, "b" * 64, now=NOW) is None
    assert (
        store.claim(
            credentials.session_id,
            credentials.token,
            ADMIN_SESSION,
            now=NOW + timedelta(seconds=61),
        )
        is None
    )
    _, expired = store.recover(now=NOW + timedelta(seconds=61))
    assert 1 == expired
    database.dispose()


def test_console_recovery_marks_active_session_interrupted(settings: Settings) -> None:
    database = _database(settings)
    store = ConsoleSessionStore(database)
    credentials = store.create(
        ADMIN_SESSION,
        "host-1",
        VM_UUID,
        ConsoleKind.SERIAL,
        now=NOW,
    )
    assert store.claim(credentials.session_id, credentials.token, ADMIN_SESSION, now=NOW)
    interrupted, expired = store.recover(now=NOW + timedelta(seconds=2))
    assert (1, 0) == (interrupted, expired)
    with database.session() as session:
        stored = session.get(ConsoleSession, credentials.session_id)
        assert stored is not None
        assert ConsoleStatus.INTERRUPTED == stored.status
    database.dispose()


def _database(settings: Settings) -> Database:
    database = Database(settings)
    upgrade_database(database)
    with database.session() as session:
        session.add(
            Host(
                id="host-1",
                name="node",
                address="node.example.test",
                ssh_port=22,
                ssh_username="root",
                authentication_method=AuthenticationMethod.PRIVATE_KEY,
                sudo_mode=SudoMode.NONE,
                libvirt_uri="qemu:///system",
                status=HostStatus.READY,
                labels_json="[]",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return database
