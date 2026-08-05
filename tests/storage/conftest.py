from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.remote.executor import RemoteExecutor
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.storage.service import StoragePoolService
from nexora.tasks.locks import ResourceLockStore
from storage.support import Audit, PoolBackend, Resolver


@pytest.fixture
def service(
    settings: Settings,
) -> Iterator[tuple[Database, StoragePoolService, PoolBackend]]:
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    backend = PoolBackend()
    executor = RemoteExecutor(
        Resolver(settings.data_dir / "hostkeys" / "known_hosts"),
        Audit(),
        backend=backend,
    )
    store = ResourceIndexStore(database)
    discovery = StorageDiscoveryService(database, executor, store)
    try:
        yield (
            database,
            StoragePoolService(
                database,
                executor,
                discovery,
                ResourceLockStore(database),
            ),
            backend,
        )
    finally:
        database.dispose()


def _add_host(database: Database) -> None:
    now = datetime.now(UTC)
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
                created_at=now,
                updated_at=now,
            )
        )
