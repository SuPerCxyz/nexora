import json
from datetime import UTC, datetime

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.remote.executor import RemoteExecutor
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.disk_changes import VmDiskChangeService
from nexora.xml import DiskDetachChange, LibvirtXmlDocument
from vms.test_cpu_changes import (
    DOMAIN_UUID,
    DOMAIN_XML,
    Audit,
    CpuBackend,
    Discovery,
    Resolver,
    _add_host,
)

POOL_UUID = "22222222-2222-2222-2222-222222222222"
VOLUME_KEY = "/images/data.qcow2"


class DiskDiscovery(Discovery):
    def run(self, _host_id: str) -> None:
        return


class StorageDiscovery:
    def run(self, _host_id: str) -> None:
        return


def test_attach_then_detach_preserves_volume_and_unknown_domain_xml(
    settings: Settings,
) -> None:
    database, service, state, vm_base, volume_base = _runtime(settings)

    preview = service.preview_attach(vm_base, volume_base, bus="virtio")
    assert "/images/data.qcow2" in preview.plan.diff_text
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=DOMAIN_UUID,
    )
    service.execute(
        preview.plan.id,
        task_id="task-attach",
        expected_change_type="disk_attach",
    )

    document = LibvirtXmlDocument.parse(state["xml"])
    disk = document.root.find("./devices/disk")
    assert disk is not None
    assert "vda" == disk.find("target").get("dev")  # type: ignore[union-attr]
    vm_base = _current_vm_base(database)
    detach = DiskDetachChange("vda", "virtio", "disk", VOLUME_KEY)
    preview = service.preview_detach(vm_base, detach)
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=DOMAIN_UUID,
    )
    service.execute(
        preview.plan.id,
        task_id="task-detach",
        expected_change_type="disk_detach",
    )

    document = LibvirtXmlDocument.parse(state["xml"])
    assert document.root.find("./devices/disk") is None
    with database.session() as session:
        volume = session.get(ResourceIndex, volume_base.resource_id)
        assert volume is not None
        assert ResourceStatus.MANAGED == volume.status
    database.dispose()


def _runtime(
    settings: Settings,
) -> tuple[
    Database,
    VmDiskChangeService,
    dict[str, bytes],
    ResourceBaseVersion,
    ResourceBaseVersion,
]:
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    state = {"xml": DOMAIN_XML}
    store = ResourceIndexStore(database)
    discovery = DiskDiscovery(state)
    result = store.apply_snapshot(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        [discovery.read_one("host-1", DOMAIN_UUID)],
    )
    vm = result.resources[0]
    _add_storage(database)
    with database.session() as session:
        volume = session.get(ResourceIndex, "volume-1")
        assert volume is not None
        volume_base = ResourceBaseVersion(
            volume.id,
            volume.host_id,
            ResourceType.STORAGE_VOLUME,
            volume.native_id,
            volume.observed_generation,
            volume.persistent_hash,
            None,
        )
    executor = RemoteExecutor(
        Resolver(settings.data_dir / "hostkeys" / "known_hosts"),
        Audit(),
        backend=CpuBackend(state),
    )
    service = VmDiskChangeService(
        database,
        executor,
        discovery,  # type: ignore[arg-type]
        store,
        ResourceWriteGuard(database),
        ResourceLockStore(database),
        StorageDiscovery(),  # type: ignore[arg-type]
    )
    vm_base = ResourceBaseVersion(
        vm.id,
        vm.host_id,
        ResourceType.VIRTUAL_MACHINE,
        vm.native_id,
        vm.observed_generation,
        vm.persistent_hash,
        vm.live_hash,
    )
    return database, service, state, vm_base, volume_base


def _add_storage(database: Database) -> None:
    now = datetime.now(UTC)
    common = {
        "host_id": "host-1",
        "status": ResourceStatus.MANAGED,
        "source": "existing",
        "observed_generation": 1,
        "labels_json": "[]",
        "first_seen_at": now,
        "last_seen_at": now,
    }
    with database.session() as session:
        session.add(
            ResourceIndex(
                id="pool-1",
                resource_type=ResourceType.STORAGE_POOL,
                native_id=POOL_UUID,
                display_name="images",
                persistent_hash="a" * 64,
                details_json=json.dumps({"pool_type": "dir", "active": True}),
                **common,
            )
        )
        session.add(
            ResourceIndex(
                id="volume-1",
                resource_type=ResourceType.STORAGE_VOLUME,
                native_id=json.dumps([POOL_UUID, VOLUME_KEY], separators=(",", ":")),
                parent_native_id=POOL_UUID,
                display_name="data.qcow2",
                persistent_hash="b" * 64,
                details_json=json.dumps(
                    {
                        "pool_uuid": POOL_UUID,
                        "key": VOLUME_KEY,
                        "path": VOLUME_KEY,
                        "format": "qcow2",
                        "capacity_bytes": 1024**3,
                    }
                ),
                **common,
            )
        )


def _current_vm_base(database: Database) -> ResourceBaseVersion:
    with database.session() as session:
        vm = session.get(ResourceIndex, _vm_resource_id(database))
        assert vm is not None
        return ResourceBaseVersion(
            vm.id,
            vm.host_id,
            ResourceType.VIRTUAL_MACHINE,
            vm.native_id,
            vm.observed_generation,
            vm.persistent_hash,
            vm.live_hash,
        )


def _vm_resource_id(database: Database) -> str:
    with database.session() as session:
        resource = (
            session.query(ResourceIndex).filter_by(resource_type=ResourceType.VIRTUAL_MACHINE).one()
        )
        return resource.id
