from uuid import UUID

import pytest

from nexora.vms.creation_contracts import VmImportCreateInput
from nexora.vms.creation_xml import build_import_domain_xml
from nexora.xml import LibvirtXmlDocument


def _input(**changes: object) -> VmImportCreateInput:
    values: dict[str, object] = {
        "host_id": "host-1",
        "pool_resource_id": "pool-1",
        "pool_uuid": "11111111-1111-1111-1111-111111111111",
        "pool_generation": 2,
        "pool_hash": "a" * 64,
        "volume_resource_id": "volume-1",
        "volume_native_id": "native-volume",
        "volume_generation": 3,
        "volume_hash": "b" * 64,
        "volume_key": "/images/system.qcow2",
        "volume_name": "system.qcow2",
        "current_capacity_bytes": 10 * 1024**3,
        "name": "created-vm",
        "memory_mib": 2048,
        "vcpus": 2,
        "vm_uuid": "22222222-2222-2222-2222-222222222222",
    }
    values.update(changes)
    return VmImportCreateInput(**values)  # type: ignore[arg-type]


def test_import_contract_round_trip_and_limits() -> None:
    create = _input()
    create.validate()
    decoded = VmImportCreateInput.decode(create.encode())

    assert create == decoded
    assert UUID(create.vm_uuid)
    with pytest.raises(ValueError, match="VM name"):
        _input(name="../escape").validate()
    with pytest.raises(ValueError, match="memory"):
        _input(memory_mib=64).validate()


def test_import_domain_xml_uses_only_structured_authority_values() -> None:
    create = _input()
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/var/lib/libvirt/images/system.qcow2",
        disk_format="qcow2",
    )
    document = LibvirtXmlDocument.parse(content, expected_root="domain")

    assert create.name == document.root.findtext("name")
    assert create.vm_uuid == document.root.findtext("uuid")
    assert "127.0.0.1" == document.root.find("devices/graphics").get("listen")  # type: ignore[union-attr]
    assert "/var/lib/libvirt/images/system.qcow2" == document.root.find("devices/disk/source").get(
        "file"
    )  # type: ignore[union-attr]
    assert document.root.find("devices/interface") is None


def test_import_domain_xml_rejects_unsupported_host_or_disk() -> None:
    with pytest.raises(ValueError, match="architecture"):
        build_import_domain_xml(
            _input(),
            architecture="ppc64le",
            disk_path="/images/system.qcow2",
            disk_format="qcow2",
        )
    with pytest.raises(ValueError, match="format"):
        build_import_domain_xml(
            _input(),
            architecture="x86_64",
            disk_path="/images/system.vmdk",
            disk_format="vmdk",
        )


@pytest.mark.parametrize(
    ("kind", "name", "attribute"),
    (("bridge", "br100", "bridge"), ("network", "default", "network")),
)
def test_import_domain_xml_adds_only_selected_virtio_network(
    kind: str,
    name: str,
    attribute: str,
) -> None:
    create = _input(
        network_kind=kind,
        network_resource_id="network-1",
        network_native_id="network-native",
        network_generation=2,
        network_hash="c" * 64,
        network_name=name,
    )

    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
    )
    interface = LibvirtXmlDocument.parse(content).root.find("devices/interface")

    assert interface is not None
    assert kind == interface.get("type")
    assert name == interface.find("source").get(attribute)  # type: ignore[union-attr]
    assert "virtio" == interface.find("model").get("type")  # type: ignore[union-attr]


def test_import_domain_xml_adds_readonly_sata_installation_iso() -> None:
    create = _input(
        iso_resource_id="iso-1",
        iso_native_id="iso-native",
        iso_generation=2,
        iso_hash="d" * 64,
        iso_key="/images/install.iso",
        iso_name="install.iso",
    )
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
        iso_path="/images/install.iso",
    )
    document = LibvirtXmlDocument.parse(content)
    cdrom = document.root.find("devices/disk[@device='cdrom']")

    assert cdrom is not None
    assert "/images/install.iso" == cdrom.find("source").get("file")  # type: ignore[union-attr]
    assert "sata" == cdrom.find("target").get("bus")  # type: ignore[union-attr]
    assert cdrom.find("readonly") is not None
    assert ["cdrom", "hd"] == [item.get("dev") for item in document.root.findall("os/boot")]


def test_import_domain_xml_defaults_to_virtio_disk_and_host_model_cpu() -> None:
    create = _input()
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
    )
    document = LibvirtXmlDocument.parse(content)
    disk = document.root.find("devices/disk")
    assert disk.get("device") == "disk"
    assert "vda" == disk.find("target").get("dev")
    assert "virtio" == disk.find("target").get("bus")
    assert "host-model" == document.root.find("cpu").get("mode")


def test_import_domain_xml_supports_sata_disk_bus() -> None:
    create = _input(disk_bus="sata")
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
    )
    document = LibvirtXmlDocument.parse(content)
    disk = document.root.find("devices/disk")
    assert "sda" == disk.find("target").get("dev")
    assert "sata" == disk.find("target").get("bus")


def test_import_domain_xml_supports_scsi_disk_bus() -> None:
    create = _input(disk_bus="scsi")
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
    )
    document = LibvirtXmlDocument.parse(content)
    disk = document.root.find("devices/disk")
    assert "sda" == disk.find("target").get("dev")
    assert "scsi" == disk.find("target").get("bus")


def test_import_domain_xml_supports_host_passthrough_cpu() -> None:
    create = _input(cpu_mode="host-passthrough")
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
    )
    document = LibvirtXmlDocument.parse(content)
    assert "host-passthrough" == document.root.find("cpu").get("mode")


def test_import_contract_rejects_invalid_disk_bus() -> None:
    with pytest.raises(ValueError, match="disk bus"):
        _input(disk_bus="ide").validate()


def test_import_contract_rejects_invalid_cpu_mode() -> None:
    with pytest.raises(ValueError, match="CPU mode"):
        _input(cpu_mode="custom").validate()


def test_import_domain_xml_generates_uefi_firmware() -> None:
    create = _input(firmware="uefi", secure_boot=False)
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
    )
    document = LibvirtXmlDocument.parse(content)
    assert "efi" == document.root.find("os").get("firmware")
    assert document.root.find("./os/loader") is None


def test_import_domain_xml_generates_tpm_device() -> None:
    create = _input(tpm2=True)
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
    )
    document = LibvirtXmlDocument.parse(content)
    tpm = document.root.find("devices/tpm")
    assert tpm is not None
    assert "tpm-crb" == tpm.get("model")
    assert "emulator" == tpm.find("backend").get("type")
    assert "2.0" == tpm.find("backend").get("version")


def test_import_domain_xml_omits_tpm_by_default() -> None:
    create = _input()
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
    )
    document = LibvirtXmlDocument.parse(content)
    assert document.root.find("devices/tpm") is None


def test_import_domain_xml_windows_uses_e1000e_network() -> None:
    create = _input(
        guest_profile="windows",
        network_kind="bridge",
        network_resource_id="network-1",
        network_native_id="network-native",
        network_generation=2,
        network_hash="c" * 64,
        network_name="br100",
    )
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
    )
    interface = LibvirtXmlDocument.parse(content).root.find("devices/interface")
    assert interface is not None
    assert "e1000e" == interface.find("model").get("type")


def test_import_domain_xml_adds_driver_iso_cdrom() -> None:
    create = _input(
        driver_iso_resource_id="driver-iso-1",
        driver_iso_native_id="driver-iso-native",
        driver_iso_generation=2,
        driver_iso_hash="e" * 64,
        driver_iso_key="/images/virtio.iso",
        driver_iso_name="virtio.iso",
    )
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
        driver_iso_path="/images/virtio.iso",
    )
    cdroms = LibvirtXmlDocument.parse(content).root.findall("devices/disk[@device='cdrom']")
    targets = [c.find("target").get("dev") for c in cdroms]
    assert "sdc" in targets


def test_import_contract_rejects_secure_boot_without_uefi() -> None:
    with pytest.raises(ValueError, match="Secure Boot requires UEFI"):
        _input(firmware="bios", secure_boot=True).validate()


def test_import_contract_rejects_invalid_guest_profile() -> None:
    with pytest.raises(ValueError, match="guest profile"):
        _input(guest_profile="bsd").validate()


def test_import_contract_rejects_invalid_firmware() -> None:
    with pytest.raises(ValueError, match="firmware"):
        _input(firmware="uefi-legacy").validate()
