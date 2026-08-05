"""Safe libvirt qcow2/raw storage volume XML generation."""

from lxml import etree

from nexora.storage.volume_contracts import StorageVolumeCreateInput
from nexora.xml.document import LibvirtXmlDocument


def build_volume_xml(create: StorageVolumeCreateInput) -> bytes:
    create.validate()
    root = etree.Element("volume", type="file")
    etree.SubElement(root, "name").text = create.name
    capacity = etree.SubElement(root, "capacity", unit="bytes")
    capacity.text = str(create.capacity_bytes)
    etree.SubElement(root, "allocation", unit="bytes").text = "0"
    target = etree.SubElement(root, "target")
    etree.SubElement(target, "format", type=create.volume_format)
    content = etree.tostring(root, encoding="utf-8")
    document = LibvirtXmlDocument.parse(content, expected_root="volume")
    return document.serialize()


def resize_volume_xml(current_xml: bytes, capacity_bytes: int) -> bytes:
    """Change only capacity while preserving every unknown XML node."""

    document = LibvirtXmlDocument.parse(current_xml, expected_root="volume")
    capacity = document.root.find("capacity")
    if capacity is None:
        raise ValueError("storage volume XML is missing capacity")
    capacity.text = str(capacity_bytes)
    capacity.set("unit", "bytes")
    return document.serialize()
