from nexora.hosts.models import Host
from nexora.media.credentials import MediaCredentialService
from nexora.media.models import MediaCredential, MediaCredentialStatus
from nexora.media.store import MediaIndexStore, MediaObservation
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.vms.platform_iso_changes import VmPlatformIsoService
from nexora.xml import LibvirtXmlDocument
from vms.test_cdrom_changes import CDROM_XML
from vms.test_disk_changes import StorageDiscovery, _current_vm_base, _runtime


def test_platform_iso_uses_source_bound_id_and_revokes_after_eject(settings) -> None:
    database, disk_service, state, _vm_base, _volume_base = _runtime(settings)
    state["xml"] = CDROM_XML
    observation = disk_service.discovery.read_one("host-1", "ignored")
    disk_service.store.refresh_one(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        observation,
    )
    with database.session() as session:
        vm = session.get(ResourceIndex, _current_vm_base(database).resource_id)
        host = session.get(Host, "host-1")
        assert vm is not None and host is not None
        vm.status = "managed"
        host.address = "192.0.2.10"
    media_store = MediaIndexStore(database)
    scan = media_store.begin()
    media_store.complete(
        scan.id,
        [
            MediaObservation(
                "iso/linux.iso",
                "linux.iso",
                "iso",
                1024,
                1,
                1,
                1,
                "c" * 64,
                None,
                None,
                (),
                "linux_iso",
                "x86_64",
            )
        ],
    )
    item = media_store.list_items()[0]
    credentials = MediaCredentialService(database)
    runtime_settings = settings.model_copy(
        update={"media_public_base_url": "https://nexora.example.test:8443"}
    )
    service = VmPlatformIsoService(
        runtime_settings,
        database,
        disk_service.executor,
        disk_service.discovery,
        disk_service.store,
        disk_service.guard,
        disk_service.locks,
        StorageDiscovery(),  # type: ignore[arg-type]
        credentials,
    )

    preview = service.preview_platform_mount(
        _current_vm_base(database),
        item.id,
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
    service.execute(preview.plan.id, task_id="platform-mount")
    document = LibvirtXmlDocument.parse(state["xml"])
    source = document.root.find("./devices/disk/source")
    assert source is not None and "https" == source.get("protocol")
    assert source.find("cookies") is None
    assert any("-blockdev driver=http" in item for item in disk_service.executor.backend.commands)
    credential_id = source.get("name", "").rsplit("/", 1)[-1]

    preview = service.preview_platform_eject(
        _current_vm_base(database),
        target="sda",
        bus="sata",
        expected_source=str(source.get("name")),
    )
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=observation.native_id,
    )
    service.execute(preview.plan.id, task_id="platform-eject")
    with database.session() as session:
        credential = session.get(MediaCredential, credential_id)
        assert credential is not None
        assert MediaCredentialStatus.REVOKED == credential.status
        assert credential.revoked_at is not None
    database.dispose()
