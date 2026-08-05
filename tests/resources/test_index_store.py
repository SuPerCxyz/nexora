from datetime import UTC, datetime

from sqlalchemy import select

from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.resources.contracts import ResourceObservation
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType


def test_snapshot_tracks_generation_change_and_missing(settings) -> None:
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    store = ResourceIndexStore(database)

    first = store.apply_snapshot(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        [_vm_observation("hash-a")],
    )
    with database.session() as session:
        item = session.scalar(select(ResourceIndex))
        assert item is not None
        item.labels_json = '["production"]'
        item.notes = "keep local metadata"
    changed = store.apply_snapshot(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        [_vm_observation("hash-b")],
    )
    missing = store.apply_snapshot("host-1", ResourceType.VIRTUAL_MACHINE, [])

    assert 1 == first.generation
    assert 2 == changed.generation
    assert 3 == missing.generation
    with database.session() as session:
        item = session.scalar(select(ResourceIndex))
        assert item is not None
        assert ResourceStatus.MISSING == item.status
        assert 3 == item.observed_generation
        assert "hash-b" == item.persistent_hash
        assert item.missing_since is not None
        assert '["production"]' == item.labels_json
        assert "keep local metadata" == item.notes
    database.dispose()


def test_unchanged_snapshot_preserves_changed_out_of_band_state(settings) -> None:
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    store = ResourceIndexStore(database)
    store.apply_snapshot("host-1", ResourceType.VIRTUAL_MACHINE, [_vm_observation("hash-a")])
    store.apply_snapshot("host-1", ResourceType.VIRTUAL_MACHINE, [_vm_observation("hash-b")])

    result = store.apply_snapshot(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        [_vm_observation("hash-b")],
    )

    assert ResourceStatus.CHANGED_OUT_OF_BAND == result.resources[0].status
    database.dispose()


def test_failed_scan_does_not_mark_previously_seen_resource_missing(settings) -> None:
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    store = ResourceIndexStore(database)
    store.apply_snapshot("host-1", ResourceType.VIRTUAL_MACHINE, [_vm_observation("hash-a")])

    scan = store.begin_scan("host-1", ResourceType.VIRTUAL_MACHINE)
    store.fail_scan(scan.id, "remote connection lost")

    with database.session() as session:
        item = session.scalar(select(ResourceIndex))
        assert item is not None
        assert ResourceStatus.MANAGED == item.status
        assert 1 == item.observed_generation
    database.dispose()


def _vm_observation(xml_hash: str) -> ResourceObservation:
    return ResourceObservation(
        native_id="11111111-1111-1111-1111-111111111111",
        display_name="existing-vm",
        status=ResourceStatus.MANAGED,
        persistent_hash=xml_hash,
        live_hash=None,
        details={"state": "shut off", "persistent": True},
        documents={"persistent_xml": b"<domain/>"},
    )


def _add_host(database: Database) -> None:
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(
            Host(
                id="host-1",
                name="node-one",
                address="node-one.example.test",
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
