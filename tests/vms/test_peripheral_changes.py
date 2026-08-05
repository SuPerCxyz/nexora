import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.remote.executor import CommandResult
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.contracts import ResourceObservation
from nexora.resources.domain_parser import parse_domain_observation
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.cpu_changes import VmChangeConflict
from nexora.vms.peripheral_changes import VmPeripheralChangeService

VM_UUID = "11111111-1111-1111-1111-111111111111"


class Executor:
    def __init__(self, realpath: str = "/srv/share") -> None:
        self.realpath = realpath

    def run(self, *_args: object, **_kwargs: object) -> CommandResult:
        return CommandResult(
            "operation", 0, self.realpath.encode(), b"", False, False, False, False, 0.1
        )


class DeviceDiscovery:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.runs = 0
        self.mutate_driver = False

    def run(self, _host_id: str) -> None:
        self.runs += 1
        if self.mutate_driver and self.runs > 1:
            with self.database.session() as session:
                device = session.scalar(
                    select(ResourceIndex).where(
                        ResourceIndex.resource_type == ResourceType.PCI_DEVICE
                    )
                )
                assert device is not None
                details = json.loads(device.details_json)
                details["driver"] = "nouveau"
                device.details_json = json.dumps(details)


class DomainDiscovery:
    def __init__(self, observation: ResourceObservation) -> None:
        self.observation = observation

    def read_one(self, *_args: object) -> ResourceObservation:
        return self.observation


class Service(VmPeripheralChangeService):
    def _validate_remote(self, _host_id: str, _proposed_xml: bytes) -> None:
        return


def test_rejects_running_vm_and_cross_host_device(settings) -> None:
    database, service, vm_base, device_base = _runtime(settings, state="running")
    with pytest.raises(VmChangeConflict, match="shutoff"):
        service.preview_host_device(vm_base, device_base, attach=True)

    wrong_host = ResourceBaseVersion(
        device_base.resource_id,
        "host-2",
        device_base.resource_type,
        device_base.native_id,
        device_base.generation,
        device_base.persistent_hash,
        device_base.live_hash,
    )
    with pytest.raises(VmChangeConflict, match="outside"):
        service._device(vm_base, wrong_host)
    database.dispose()


@pytest.mark.parametrize(
    ("details", "message"),
    [
        ({"driver": "vfio-pci", "iommu_group": None}, "IOMMU"),
        ({"driver": "nouveau", "iommu_group": "12"}, "vfio-pci"),
    ],
)
def test_rejects_unsafe_pci_device(settings, details, message) -> None:
    database, service, vm_base, device_base = _runtime(settings, device_details=details)
    with pytest.raises(VmChangeConflict, match=message):
        service.preview_host_device(vm_base, device_base, attach=True)
    database.dispose()


def test_rejects_unauthorized_or_changed_shared_root(settings) -> None:
    database, service, vm_base, _device_base = _runtime(settings)
    with pytest.raises(VmChangeConflict, match="not authorized"):
        service.preview_shared_directory(
            vm_base,
            root_index=-1,
            target_tag="shared",
            driver="virtiofs",
            readonly=False,
            attach=True,
        )

    service.executor.realpath = "/srv/other"  # type: ignore[attr-defined]
    with pytest.raises(VmChangeConflict, match="realpath differs"):
        service.preview_shared_directory(
            vm_base,
            root_index=0,
            target_tag="shared",
            driver="virtiofs",
            readonly=False,
            attach=True,
        )
    database.dispose()


def test_rejects_device_referenced_with_reordered_address_attributes(settings) -> None:
    database, service, vm_base, device_base = _runtime(settings, referenced=True)
    with pytest.raises(VmChangeConflict, match="already referenced"):
        service.preview_host_device(vm_base, device_base, attach=True)
    database.dispose()


def test_execute_revalidates_pci_driver(settings) -> None:
    database, service, vm_base, device_base = _runtime(settings)
    preview = service.preview_host_device(vm_base, device_base, attach=True)
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=VM_UUID,
    )
    service.device_discovery.mutate_driver = True  # type: ignore[attr-defined]

    with pytest.raises(VmChangeConflict, match="vfio-pci"):
        service.execute(preview.plan.id, task_id="task-device")
    database.dispose()


def _runtime(
    settings,
    *,
    state: str = "shut off",
    device_details: dict[str, object] | None = None,
    referenced: bool = False,
):
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    store = ResourceIndexStore(database)
    vm_observation = _vm_observation(state=state)
    vm_result = store.apply_snapshot("host-1", ResourceType.VIRTUAL_MACHINE, [vm_observation])
    device_result = store.apply_snapshot(
        "host-1",
        ResourceType.PCI_DEVICE,
        [_device_observation(device_details)],
    )
    if referenced:
        store.apply_snapshot(
            "host-1",
            ResourceType.VIRTUAL_MACHINE,
            [vm_observation, _vm_observation(uuid="22222222-2222-2222-2222-222222222222")],
        )
    vm = vm_result.resources[0]
    device = device_result.resources[0]
    discovery = DeviceDiscovery(database)
    executor = Executor()
    service = Service(
        database,
        executor,  # type: ignore[arg-type]
        DomainDiscovery(vm_observation),  # type: ignore[arg-type]
        store,
        ResourceWriteGuard(database),
        ResourceLockStore(database),
        discovery,  # type: ignore[arg-type]
        ("/srv/share",),
    )
    return (
        database,
        service,
        _base(vm),
        _base(device),
    )


def _base(resource: ResourceIndex) -> ResourceBaseVersion:
    return ResourceBaseVersion(
        resource.id,
        resource.host_id,
        ResourceType(resource.resource_type),
        resource.native_id,
        resource.observed_generation,
        resource.persistent_hash,
        resource.live_hash,
    )


def _vm_observation(
    *,
    uuid: str = VM_UUID,
    state: str = "shut off",
) -> ResourceObservation:
    hostdev = ""
    if uuid != VM_UUID:
        hostdev = (
            '<hostdev type="pci" mode="subsystem"><source>'
            '<address function="0x0" slot="0x00" bus="0x03" domain="0x0000"/>'
            "</source></hostdev>"
        )
    xml = (
        f'<domain type="kvm"><name>vm-{uuid[:4]}</name><uuid>{uuid}</uuid>'
        f"<devices>{hostdev}</devices></domain>"
    ).encode()
    return parse_domain_observation(
        uuid,
        xml,
        None,
        state=state,
        autostart=False,
    )


def _device_observation(
    details: dict[str, object] | None,
) -> ResourceObservation:
    resolved = details or {"driver": "vfio-pci", "iommu_group": "12"}
    return ResourceObservation(
        native_id="0000:03:00.0",
        display_name="pci_0000_03_00_0",
        status=ResourceStatus.READ_ONLY,
        persistent_hash="device-hash",
        live_hash=None,
        details=resolved,
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
