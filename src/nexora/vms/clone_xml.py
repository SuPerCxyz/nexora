"""Preservation-oriented XML transformation for full VM clones."""

import copy
import difflib
from collections.abc import Mapping, Sequence

from lxml import etree

from nexora.xml import LibvirtXmlDocument


def build_clone_xml(
    source_xml: bytes,
    *,
    name: str,
    vm_uuid: str,
    disk_paths: Mapping[str, str],
    nvram_path: str | None,
    mac_addresses: Sequence[str],
) -> bytes:
    document = LibvirtXmlDocument.parse(source_xml, expected_root="domain")
    root = copy.deepcopy(document.root)
    _set_text(root, "name", name)
    _set_text(root, "uuid", vm_uuid)
    _strip_host_specific(root)
    interfaces = root.findall("./devices/interface")
    if len(interfaces) != len(mac_addresses):
        raise ValueError("clone MAC address count does not match interfaces")
    for disk in root.findall("./devices/disk[@type='file']"):
        source = disk.find("source")
        if source is None:
            continue
        old_path = source.get("file")
        if old_path is not None and old_path in disk_paths:
            source.set("file", disk_paths[old_path])
    for interface, mac in zip(interfaces, mac_addresses, strict=True):
        mac_element = interface.find("mac")
        if mac_element is None:
            mac_element = etree.Element("mac")
            interface.insert(0, mac_element)
        mac_element.set("address", mac)
        target = interface.find("target")
        if target is not None:
            interface.remove(target)
    nvram = root.find("./os/nvram")
    if nvram is not None and nvram_path is not None:
        nvram.text = nvram_path
    return LibvirtXmlDocument(
        root.getroottree(),
        document.limits,
    ).serialize()


def _strip_host_specific(root: etree._Element) -> None:
    """Remove emulator path and machine type so target libvirt auto-detects."""

    emulator = root.find("./devices/emulator")
    parent = emulator.getparent() if emulator is not None else None
    if parent is not None:
        parent.remove(emulator)  # type: ignore[arg-type]
    os_type = root.find("./os/type")
    if os_type is not None and "machine" in os_type.attrib:
        del os_type.attrib["machine"]


def clone_xml_diff(source_xml: bytes, target_xml: bytes) -> str:
    before = source_xml.decode("utf-8").splitlines()
    after = target_xml.decode("utf-8").splitlines()
    return "\n".join(
        difflib.unified_diff(before, after, fromfile="source.xml", tofile="clone.xml", lineterm="")
    )


def _set_text(root: etree._Element, name: str, value: str) -> None:
    element = root.find(name)
    if element is None:
        raise ValueError(f"source VM XML is missing {name}")
    element.text = value
