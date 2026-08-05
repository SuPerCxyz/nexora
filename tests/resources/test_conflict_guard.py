from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.resources.conflicts import (
    ResourceBaseVersion,
    ResourceWriteConflict,
    ResourceWriteGuard,
)
from nexora.resources.contracts import ResourceObservation
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType


def test_guard_accepts_newer_generation_when_persistent_hash_is_unchanged(settings) -> None:
    database, _resource, base = _indexed(settings)
    ResourceIndexStore(database).apply_snapshot(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        [_observation("hash-a")],
    )

    verified = ResourceWriteGuard(database).verify(base)

    assert 2 == verified.generation
    database.dispose()


def test_guard_rejects_out_of_band_hash_change(settings) -> None:
    database, _resource, base = _indexed(settings)
    ResourceIndexStore(database).apply_snapshot(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        [_observation("hash-b")],
    )

    with pytest.raises(ResourceWriteConflict) as caught:
        ResourceWriteGuard(database).verify(base)

    assert "status blocks writes" in caught.value.reason
    assert "hash-b" == caught.value.current_hash
    database.dispose()


def test_guard_rejects_cross_host_identity_even_with_resource_id(settings) -> None:
    database, resource, base = _indexed(settings)
    wrong_scope = ResourceBaseVersion(
        resource.id,
        "other-host",
        base.resource_type,
        base.native_id,
        base.generation,
        base.persistent_hash,
        base.live_hash,
    )

    with pytest.raises(ResourceWriteConflict, match="identity"):
        ResourceWriteGuard(database).verify(wrong_scope)
    database.dispose()


def _indexed(settings) -> tuple[Database, ResourceIndex, ResourceBaseVersion]:
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    result = ResourceIndexStore(database).apply_snapshot(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        [_observation("hash-a")],
    )
    with database.session() as session:
        resource = session.scalar(select(ResourceIndex))
        assert resource is not None
    base = ResourceBaseVersion(
        resource.id,
        resource.host_id,
        ResourceType.VIRTUAL_MACHINE,
        resource.native_id,
        result.generation,
        resource.persistent_hash,
        resource.live_hash,
    )
    return database, resource, base


def _observation(value: str) -> ResourceObservation:
    return ResourceObservation(
        native_id="11111111-1111-1111-1111-111111111111",
        display_name="vm",
        status=ResourceStatus.MANAGED,
        persistent_hash=value,
        live_hash=None,
    )


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
