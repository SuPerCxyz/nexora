from nexora.media.store import MediaIndexStore, MediaObservation
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.vms.cached_iso_changes import VmCachedIsoService
from vms.test_cdrom_changes import CDROM_XML
from vms.test_disk_changes import StorageDiscovery, _current_vm_base, _runtime


class Transfer:
    def upload(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("preview must not transfer media")


def test_cached_iso_preview_uses_deterministic_managed_path(settings) -> None:
    database, disk_service, state, _vm_base, _volume_base = _runtime(settings)
    state["xml"] = CDROM_XML
    observation = disk_service.discovery.read_one("host-1", "ignored")
    disk_service.store.refresh_one("host-1", ResourceType.VIRTUAL_MACHINE, observation)
    with database.session() as session:
        vm = session.get(ResourceIndex, _current_vm_base(database).resource_id)
        assert vm is not None
        vm.status = "managed"
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
    service = VmCachedIsoService(
        settings,
        database,
        disk_service.executor,
        Transfer(),  # type: ignore[arg-type]
        disk_service.discovery,
        disk_service.store,
        disk_service.guard,
        disk_service.locks,
        StorageDiscovery(),  # type: ignore[arg-type]
    )

    preview = service.preview_cached_mount(
        _current_vm_base(database),
        item.id,
        target="sda",
        bus="sata",
        expected_source=None,
    )

    expected = f"/var/tmp/nexora-media-{'c' * 64}.iso"
    assert expected in preview.plan.diff_text
    assert "cdrom_cache_mount" == preview.plan.change_type
    database.dispose()
