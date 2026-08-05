import pytest

from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.resources.snapshot_parser import parse_snapshot_observation
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.snapshot_contracts import (
    SnapshotCreateInput,
    SnapshotDeleteInput,
    SnapshotRevertInput,
)
from nexora.vms.snapshot_delete_service import SnapshotDeleteService
from nexora.vms.snapshot_errors import SnapshotChangeError
from nexora.vms.snapshot_models import SnapshotChangePlan
from nexora.vms.snapshot_revert_service import SnapshotRevertService
from nexora.vms.snapshot_service import SnapshotService
from vms.test_disk_changes import _current_vm_base, _runtime

SNAPSHOT_DOMAIN_XML = b"""<domain type="kvm">
  <name>vm-one</name><uuid>11111111-1111-1111-1111-111111111111</uuid>
  <memory unit="KiB">4194304</memory><vcpu current="2">4</vcpu>
  <devices><disk type="file" device="disk">
    <driver name="qemu" type="qcow2"/>
    <source file="/images/data.qcow2"/><target dev="vda" bus="virtio"/>
  </disk><mystery preserve="yes"/></devices>
</domain>"""
SNAPSHOT_XML = (
    b"""<domainsnapshot>
  <name>before-upgrade</name><state>shutoff</state>
  <creationTime>1700000000</creationTime><memory snapshot="no"/>
  <disks><disk name="vda" snapshot="internal"/></disks>"""
    + SNAPSHOT_DOMAIN_XML
    + b"</domainsnapshot>"
)


class SnapshotDiscovery:
    def __init__(self, store, backend, *, existing: bool = False) -> None:
        self.store = store
        self.backend = backend
        self.existing = existing

    def run(self, host_id: str) -> None:
        observations = []
        created = any("snapshot-create-as" in command for command in self.backend.commands)
        deleted = any("snapshot-delete" in command for command in self.backend.commands)
        if (self.existing or created) and not deleted:
            observations.append(
                parse_snapshot_observation(
                    "11111111-1111-1111-1111-111111111111",
                    "before-upgrade",
                    SNAPSHOT_XML,
                    current=True,
                )
            )
        self.store.apply_snapshot(host_id, ResourceType.SNAPSHOT, observations)


def test_snapshot_create_uses_confirmed_plan_and_verifies_internal_mode(settings) -> None:
    database, disk_service, state, _vm_base, _volume_base = _runtime(settings)
    state["xml"] = SNAPSHOT_DOMAIN_XML
    observation = disk_service.discovery.read_one("host-1", "ignored")
    disk_service.store.refresh_one("host-1", ResourceType.VIRTUAL_MACHINE, observation)
    with database.session() as session:
        vm = session.get(ResourceIndex, _current_vm_base(database).resource_id)
        assert vm is not None
        vm.status = "managed"
    snapshots = SnapshotDiscovery(
        disk_service.store,
        disk_service.executor.backend,
    )
    service = SnapshotService(
        database,
        disk_service.executor,
        disk_service.discovery,
        snapshots,  # type: ignore[arg-type]
        disk_service.store,
        disk_service.guard,
        disk_service.locks,
    )
    create = SnapshotCreateInput(
        _current_vm_base(database),
        "before-upgrade",
        "Before package upgrade",
    )
    preview = service.preview_create(create)
    assert "disk: vda internal" in preview.plan.diff_text
    service.confirm_create(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=create.vm_base.native_id,
    )
    result = service.execute_create(preview.plan.id, task_id="snapshot-create")
    assert "Snapshot created" in result
    with database.session() as session:
        plan = session.get(SnapshotChangePlan, preview.plan.id)
        snapshot = (
            session.query(ResourceIndex)
            .filter_by(
                host_id="host-1",
                resource_type=ResourceType.SNAPSHOT,
                display_name="before-upgrade",
            )
            .one()
        )
        assert plan is not None and VmChangePlanStatus.SUCCEEDED == plan.status
        assert snapshot.parent_native_id == create.vm_base.native_id
    assert any(
        "snapshot-create-as" in command and "before-upgrade" in command and "--atomic" in command
        for command in disk_service.executor.backend.commands
    )
    database.dispose()


def test_snapshot_delete_requires_leaf_baseline_and_verifies_missing(settings) -> None:
    database, disk_service, state, _vm_base, _volume_base = _runtime(settings)
    state["xml"] = SNAPSHOT_DOMAIN_XML
    observation = disk_service.discovery.read_one("host-1", "ignored")
    disk_service.store.refresh_one("host-1", ResourceType.VIRTUAL_MACHINE, observation)
    with database.session() as session:
        vm = session.get(ResourceIndex, _current_vm_base(database).resource_id)
        assert vm is not None
        vm.status = "managed"
    snapshots = SnapshotDiscovery(
        disk_service.store,
        disk_service.executor.backend,
        existing=True,
    )
    snapshots.run("host-1")
    with database.session() as session:
        snapshot = (
            session.query(ResourceIndex)
            .filter_by(
                host_id="host-1",
                resource_type=ResourceType.SNAPSHOT,
                display_name="before-upgrade",
            )
            .one()
        )
        snapshot_base = ResourceBaseVersion(
            snapshot.id,
            "host-1",
            ResourceType.SNAPSHOT,
            snapshot.native_id,
            snapshot.observed_generation,
            str(snapshot.persistent_hash),
            None,
        )
    service = SnapshotDeleteService(
        database,
        disk_service.executor,
        disk_service.discovery,
        snapshots,  # type: ignore[arg-type]
        disk_service.store,
        disk_service.guard,
        disk_service.locks,
    )
    delete = SnapshotDeleteInput(
        _current_vm_base(database),
        snapshot_base,
        "before-upgrade",
    )
    preview = service.preview(delete)
    assert "delete internal leaf Snapshot" in preview.plan.diff_text
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=delete.vm_base.native_id,
        snapshot_name=delete.name,
    )
    result = service.execute(preview.plan.id, task_id="snapshot-delete")
    assert "Snapshot deleted" in result
    with database.session() as session:
        stored = session.get(ResourceIndex, snapshot_base.resource_id)
        assert stored is not None and stored.status == "missing"
    assert any(
        "snapshot-delete" in command and "before-upgrade" in command
        for command in disk_service.executor.backend.commands
    )
    database.dispose()


def test_snapshot_revert_requires_name_and_avoids_force_flags(settings) -> None:
    database, disk_service, state, _vm_base, _volume_base = _runtime(settings)
    state["xml"] = SNAPSHOT_DOMAIN_XML
    observation = disk_service.discovery.read_one("host-1", "ignored")
    disk_service.store.refresh_one("host-1", ResourceType.VIRTUAL_MACHINE, observation)
    with database.session() as session:
        vm = session.get(ResourceIndex, _current_vm_base(database).resource_id)
        assert vm is not None
        vm.status = "managed"
    snapshots = SnapshotDiscovery(
        disk_service.store,
        disk_service.executor.backend,
        existing=True,
    )
    snapshots.run("host-1")
    with database.session() as session:
        snapshot = (
            session.query(ResourceIndex)
            .filter_by(
                host_id="host-1",
                resource_type=ResourceType.SNAPSHOT,
                display_name="before-upgrade",
            )
            .one()
        )
        snapshot_base = ResourceBaseVersion(
            snapshot.id,
            "host-1",
            ResourceType.SNAPSHOT,
            snapshot.native_id,
            snapshot.observed_generation,
            str(snapshot.persistent_hash),
            None,
        )
    service = SnapshotRevertService(
        database,
        disk_service.executor,
        disk_service.discovery,
        snapshots,  # type: ignore[arg-type]
        disk_service.store,
        disk_service.guard,
        disk_service.locks,
    )
    revert = SnapshotRevertInput(
        _current_vm_base(database),
        snapshot_base,
        "before-upgrade",
    )
    preview = service.preview(revert)
    with pytest.raises(SnapshotChangeError, match="VM name"):
        service.confirm(
            preview.plan.id,
            preview.confirmation_token,
            host_id="host-1",
            vm_uuid=revert.vm_base.native_id,
            snapshot_name=revert.name,
            confirmation_name="wrong-name",
        )
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=revert.vm_base.native_id,
        snapshot_name=revert.name,
        confirmation_name="vm-one",
    )
    result = service.execute(preview.plan.id, task_id="snapshot-revert")
    assert "Snapshot reverted" in result
    command = next(
        item for item in disk_service.executor.backend.commands if "snapshot-revert" in item
    )
    assert "--force" not in command and "--running" not in command
    database.dispose()
