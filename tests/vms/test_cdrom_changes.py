import json

from nexora.config import Settings
from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.vms.cdrom_changes import VmCdromChangeService
from nexora.xml import LibvirtXmlDocument
from vms.test_disk_changes import StorageDiscovery, _current_vm_base, _runtime

CDROM_XML = b"""<domain type="kvm">
  <name>vm-one</name><uuid>11111111-1111-1111-1111-111111111111</uuid>
  <memory unit="KiB">4194304</memory><vcpu current="2">4</vcpu>
  <devices><disk type="file" device="cdrom">
    <driver name="qemu" type="raw"/>
    <target dev="sda" bus="sata" tray="open"/>
    <readonly/><address type="drive" controller="0" bus="0" target="0" unit="0"/>
  </disk><mystery preserve="yes"/></devices>
</domain>"""
ISO_PATH = "/images/installer.iso"


def test_mount_then_eject_local_iso_preserves_volume_and_cdrom(
    settings: Settings,
) -> None:
    database, disk_service, state, _vm_base, volume_base = _runtime(settings)
    state["xml"] = CDROM_XML
    observation = disk_service.discovery.read_one("host-1", volume_base.native_id)
    disk_service.store.refresh_one(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        observation,
    )
    with database.session() as session:
        vm = session.get(ResourceIndex, _current_vm_base(database).resource_id)
        assert vm is not None
        vm.status = "managed"
        volume = session.get(ResourceIndex, volume_base.resource_id)
        assert volume is not None
        volume.display_name = "installer.iso"
        details = json.loads(volume.details_json)
        details.update(path=ISO_PATH, key=ISO_PATH, format="raw")
        volume.details_json = json.dumps(details)
        volume.native_id = json.dumps(
            [details["pool_uuid"], ISO_PATH],
            separators=(",", ":"),
        )
        volume_base = ResourceBaseVersion(
            volume.id,
            volume.host_id,
            ResourceType.STORAGE_VOLUME,
            volume.native_id,
            volume.observed_generation,
            volume.persistent_hash,
            None,
        )
    service = VmCdromChangeService(
        database,
        disk_service.executor,
        disk_service.discovery,
        disk_service.store,
        disk_service.guard,
        disk_service.locks,
        StorageDiscovery(),  # type: ignore[arg-type]
    )

    preview = service.preview_mount(
        _current_vm_base(database),
        volume_base,
        target="sda",
        bus="sata",
        expected_source=None,
    )
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=observation.native_id,
    )
    service.execute(preview.plan.id, task_id="mount")
    document = LibvirtXmlDocument.parse(state["xml"])
    assert ISO_PATH == document.root.find("./devices/disk/source").get("file")  # type: ignore[union-attr]

    preview = service.preview_eject(
        _current_vm_base(database),
        target="sda",
        bus="sata",
        expected_source=ISO_PATH,
    )
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=observation.native_id,
    )
    service.execute(preview.plan.id, task_id="eject")
    document = LibvirtXmlDocument.parse(state["xml"])
    assert document.root.find("./devices/disk/source") is None
    assert document.root.find("./devices/mystery") is not None
    database.dispose()
