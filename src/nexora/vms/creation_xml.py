"""Structured libvirt Domain XML generation for managed-volume imports."""

from lxml import etree

from nexora.vms.creation_contracts import VmCreationOptions


def build_import_domain_xml(
    create: VmCreationOptions,
    *,
    architecture: str,
    disk_path: str,
    disk_format: str,
    iso_path: str | None = None,
    cloud_init_path: str | None = None,
    driver_iso_path: str | None = None,
    uefi_loader: str | None = None,
    uefi_vars_template: str | None = None,
    uefi_secure: bool = False,
) -> bytes:
    if architecture not in {"x86_64", "aarch64"}:
        raise ValueError("host architecture is not supported for VM creation")
    if disk_format not in {"qcow2", "raw"}:
        raise ValueError("disk format is not supported for VM creation")
    root = etree.Element("domain", type="kvm")
    _text(root, "name", create.name)
    _text(root, "uuid", create.vm_uuid)
    _text(root, "memory", str(create.memory_mib), unit="MiB")
    _text(root, "currentMemory", str(create.memory_mib), unit="MiB")
    _text(root, "vcpu", str(create.vcpus), placement="static")
    _os_element(root, create, architecture, iso_path, uefi_loader, uefi_vars_template, uefi_secure)
    etree.SubElement(root, "cpu", mode=create.cpu_mode, check="partial")
    features = etree.SubElement(root, "features")
    etree.SubElement(features, "acpi")
    if architecture == "x86_64":
        etree.SubElement(features, "apic")
    if create.secure_boot:
        etree.SubElement(features, "smm", state="on")
    _text(root, "on_poweroff", "destroy")
    _text(root, "on_reboot", "restart")
    _text(root, "on_crash", "destroy")
    devices = etree.SubElement(root, "devices")
    _system_disk(devices, create, disk_path, disk_format)
    _installation_cdrom(devices, iso_path)
    _driver_iso_cdrom(devices, driver_iso_path)
    _cloud_init_cdrom(devices, cloud_init_path)
    _network_interface(devices, create)
    _tpm_device(devices, create)
    etree.SubElement(devices, "serial", type="pty")
    console = etree.SubElement(devices, "console", type="pty")
    etree.SubElement(console, "target", type="serial", port="0")
    channel = etree.SubElement(devices, "channel", type="unix")
    etree.SubElement(channel, "target", type="virtio", name="org.qemu.guest_agent.0")
    etree.SubElement(
        devices,
        "graphics",
        type="vnc",
        port="-1",
        autoport="yes",
        listen="127.0.0.1",
    )
    etree.SubElement(devices, "memballoon", model="virtio")
    return etree.tostring(root, encoding="UTF-8", pretty_print=True)


def creation_diff(content: bytes) -> str:
    return "\n".join(f"+ {line}" for line in content.decode("utf-8").splitlines())


def _network_interface(
    devices: etree._Element,
    create: VmCreationOptions,
) -> None:
    if create.network_kind == "none":
        return
    if create.network_name is None:
        raise ValueError("VM network name is unavailable")
    interface = etree.SubElement(devices, "interface", type=create.network_kind)
    if create.network_mac is not None:
        etree.SubElement(interface, "mac", address=create.network_mac)
    source_attribute = "bridge" if create.network_kind == "bridge" else "network"
    etree.SubElement(interface, "source", attrib={source_attribute: create.network_name})
    model = "e1000e" if create.guest_profile == "windows" else "virtio"
    etree.SubElement(interface, "model", type=model)


def _os_element(
    root: etree._Element,
    create: VmCreationOptions,
    architecture: str,
    iso_path: str | None,
    uefi_loader: str | None,
    uefi_vars_template: str | None,
    uefi_secure: bool,
) -> None:
    os_element = etree.SubElement(root, "os")
    if create.firmware == "uefi" and uefi_loader is not None:
        _text(os_element, "type", "hvm", arch=architecture)
        loader = etree.SubElement(
            os_element,
            "loader",
            readonly="yes",
            secure="yes" if uefi_secure else "no",
            type="pflash",
        )
        loader.text = uefi_loader
        if uefi_vars_template is not None:
            nvram = etree.SubElement(os_element, "nvram", template=uefi_vars_template)
            nvram.text = f".nexora-nvram-{create.vm_uuid}.fd"
    elif create.firmware == "uefi":
        _text(os_element, "type", "hvm", arch=architecture)
        os_element.set("firmware", "efi")
    else:
        _text(os_element, "type", "hvm", arch=architecture)
    if iso_path is not None:
        etree.SubElement(os_element, "boot", dev="cdrom")
    etree.SubElement(os_element, "boot", dev="hd")


def _system_disk(
    devices: etree._Element,
    create: VmCreationOptions,
    disk_path: str,
    disk_format: str,
) -> None:
    disk = etree.SubElement(devices, "disk", type="file", device="disk")
    etree.SubElement(disk, "driver", name="qemu", type=disk_format)
    etree.SubElement(disk, "source", file=disk_path)
    bus = create.disk_bus
    target_dev = "vda" if bus == "virtio" else "sda"
    etree.SubElement(disk, "target", dev=target_dev, bus=bus)


def _driver_iso_cdrom(devices: etree._Element, path: str | None) -> None:
    if path is None:
        return
    cdrom = etree.SubElement(devices, "disk", type="file", device="cdrom")
    etree.SubElement(cdrom, "driver", name="qemu", type="raw")
    etree.SubElement(cdrom, "source", file=path)
    etree.SubElement(cdrom, "target", dev="sdc", bus="sata")
    etree.SubElement(cdrom, "readonly")


def _tpm_device(devices: etree._Element, create: VmCreationOptions) -> None:
    if not create.tpm2:
        return
    tpm = etree.SubElement(devices, "tpm", model="tpm-crb")
    etree.SubElement(tpm, "backend", type="emulator", version="2.0")


def _installation_cdrom(devices: etree._Element, iso_path: str | None) -> None:
    if iso_path is None:
        return
    cdrom = etree.SubElement(devices, "disk", type="file", device="cdrom")
    etree.SubElement(cdrom, "driver", name="qemu", type="raw")
    etree.SubElement(cdrom, "source", file=iso_path)
    etree.SubElement(cdrom, "target", dev="sda", bus="sata")
    etree.SubElement(cdrom, "readonly")


def _cloud_init_cdrom(devices: etree._Element, path: str | None) -> None:
    if path is None:
        return
    cdrom = etree.SubElement(devices, "disk", type="file", device="cdrom")
    etree.SubElement(cdrom, "driver", name="qemu", type="raw")
    etree.SubElement(cdrom, "source", file=path)
    etree.SubElement(cdrom, "target", dev="sdb", bus="sata")
    etree.SubElement(cdrom, "readonly")


def _text(parent: etree._Element, name: str, value: str, **attributes: str) -> None:
    element = etree.SubElement(parent, name, attrib=attributes)
    element.text = value
