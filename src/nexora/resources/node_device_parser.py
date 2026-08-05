"""Safe parsing of libvirt PCI and USB node-device XML."""

import json

from lxml import etree

from nexora.resources.contracts import ResourceObservation
from nexora.resources.models import ResourceStatus, ResourceType
from nexora.xml.document import HASH_ALGORITHM, LibvirtXmlDocument
from nexora.xml.errors import XmlStructureError


def parse_node_device(
    content: bytes,
    expected_type: ResourceType,
) -> ResourceObservation:
    document = LibvirtXmlDocument.parse(content, expected_root="device")
    capability = document.root.find(f"./capability[@type='{_capability(expected_type)}']")
    if capability is None:
        raise XmlStructureError("node device does not contain the requested capability")
    name = _required_text(document.root, "name")
    driver = document.root.findtext("./driver/name")
    if expected_type == ResourceType.PCI_DEVICE:
        native_id, details = _pci(capability)
    elif expected_type == ResourceType.USB_DEVICE:
        native_id, details = _usb(capability)
    else:
        raise ValueError("unsupported node-device resource type")
    return ResourceObservation(
        native_id=native_id,
        display_name=name,
        status=ResourceStatus.READ_ONLY,
        persistent_hash=document.fingerprint().digest,
        live_hash=None,
        hash_algorithm=HASH_ALGORITHM,
        details={"name": name, "driver": driver, **details},
        documents={"node_device_xml": content},
    )


def _pci(capability: etree._Element) -> tuple[str, dict[str, object]]:
    domain = _number(capability, "domain")
    bus = _number(capability, "bus")
    slot = _number(capability, "slot")
    function = _number(capability, "function")
    address = f"{domain:04x}:{bus:02x}:{slot:02x}.{function:x}"
    iommu = capability.find("iommuGroup")
    return address, {
        "address": address,
        "class": capability.findtext("class"),
        "vendor_id": _attribute(capability, "vendor", "id"),
        "vendor": capability.findtext("vendor"),
        "product_id": _attribute(capability, "product", "id"),
        "product": capability.findtext("product"),
        "iommu_group": iommu.get("number") if iommu is not None else None,
    }


def _usb(capability: etree._Element) -> tuple[str, dict[str, object]]:
    bus = _number(capability, "bus")
    device = _number(capability, "device")
    vendor_id = _attribute(capability, "vendor", "id")
    product_id = _attribute(capability, "product", "id")
    native_id = json.dumps(
        [bus, device, vendor_id, product_id],
        separators=(",", ":"),
    )
    return native_id, {
        "bus": bus,
        "device": device,
        "vendor_id": vendor_id,
        "vendor": capability.findtext("vendor"),
        "product_id": product_id,
        "product": capability.findtext("product"),
    }


def _capability(resource_type: ResourceType) -> str:
    if resource_type == ResourceType.PCI_DEVICE:
        return "pci"
    if resource_type == ResourceType.USB_DEVICE:
        return "usb_device"
    raise ValueError("unsupported node-device resource type")


def _required_text(element: etree._Element, path: str) -> str:
    value = element.findtext(path)
    if value is None or not value.strip():
        raise XmlStructureError(f"node-device XML is missing {path}")
    return value.strip()


def _number(element: etree._Element, path: str) -> int:
    value = _required_text(element, path)
    try:
        return int(value, 0)
    except ValueError as exc:
        raise XmlStructureError(f"node-device {path} is invalid") from exc


def _attribute(element: etree._Element, path: str, attribute: str) -> str | None:
    child = element.find(path)
    return child.get(attribute) if child is not None else None
