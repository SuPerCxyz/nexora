"""Structural verification for a newly defined VM."""

from nexora.vms.creation_contracts import VmCreationOptions


def created_vm_matches(
    details: dict[str, object],
    create: VmCreationOptions,
    *,
    disk_path: str,
    iso_path: str,
    cloud_init_path: str = "",
) -> bool:
    disks = details.get("disks")
    if not isinstance(disks, list):
        return False
    system_target = "vda" if create.disk_bus == "virtio" else "sda"
    system_disk = any(
        isinstance(disk, dict)
        and disk.get("source") == disk_path
        and disk.get("format") in {"qcow2", "raw"}
        and disk.get("target") == system_target
        for disk in disks
    )
    return (
        bool(details.get("persistent"))
        and str(details.get("state", "")).lower() in {"shut off", "shutoff"}
        and details.get("maximum_vcpus") == create.vcpus
        and details.get("memory_kib") == create.memory_mib * 1024
        and system_disk
        and _network_matches(details.get("interfaces"), create)
        and _cdroms_match(disks, create, iso_path, cloud_init_path)
    )


def _network_matches(interfaces: object, create: VmCreationOptions) -> bool:
    if not isinstance(interfaces, list):
        return create.network_kind == "none"
    if create.network_kind == "none":
        return not interfaces
    expected_model = "e1000e" if create.guest_profile == "windows" else "virtio"
    return any(
        isinstance(interface, dict)
        and interface.get("type") == create.network_kind
        and interface.get("source") == create.network_name
        and interface.get("model") == expected_model
        and (
            create.network_mac is None
            or str(interface.get("mac", "")).lower() == create.network_mac.lower()
        )
        for interface in interfaces
    )


def _cdroms_match(
    disks: list[object],
    create: VmCreationOptions,
    iso_path: str,
    cloud_init_path: str,
) -> bool:
    expected = {
        path: target
        for path, target in (
            (iso_path if create.iso_resource_id is not None else "", "sda"),
            (cloud_init_path, "sdb"),
        )
        if path
    }
    actual = {
        str(disk.get("source")): str(disk.get("target"))
        for disk in disks
        if isinstance(disk, dict) and disk.get("device") == "cdrom"
    }
    if actual != expected:
        return False
    return all(
        disk.get("bus") == "sata" and bool(disk.get("readonly"))
        for disk in disks
        if isinstance(disk, dict) and disk.get("device") == "cdrom"
    )
