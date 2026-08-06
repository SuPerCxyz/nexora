"""Network change live device extraction and update path tests."""

from io import BytesIO

from lxml import etree

from nexora.vms.network_changes import _extract_interface_xml
from nexora.xml import LibvirtXmlDocument

DOMAIN = b"""\
<domain type="kvm">
  <name>vm</name>
  <devices>
    <interface type="network">
      <mac address="52:54:00:aa:bb:cc"/>
      <source network="default"/>
      <model type="virtio"/>
    </interface>
  </devices>
</domain>"""


def test_live_update_extracts_interface_by_new_mac() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    interface = document.root.find("devices/interface")
    assert interface is not None
    mac = interface.find("mac")
    assert mac is not None
    mac.set("address", "52:54:00:dd:ee:ff")

    payload: dict[str, object] = {"mac": "52:54:00:aa:bb:cc", "new_mac": "52:54:00:dd:ee:ff"}
    extracted = _extract_interface_xml(document.serialize(), "interface_update", payload)
    tree = etree.parse(BytesIO(extracted))
    assert tree.getroot().find("mac").get("address") == "52:54:00:dd:ee:ff"  # type: ignore[union-attr]


def test_live_update_extracts_interface_by_unchanged_mac() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    payload: dict[str, object] = {"mac": "52:54:00:aa:bb:cc"}
    extracted = _extract_interface_xml(document.serialize(), "interface_update", payload)
    tree = etree.parse(BytesIO(extracted))
    assert tree.getroot().find("mac").get("address") == "52:54:00:aa:bb:cc"  # type: ignore[union-attr]


def test_live_detach_extracts_interface_from_original_xml() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    payload: dict[str, object] = {"mac": "52:54:00:aa:bb:cc"}
    extracted = _extract_interface_xml(document.serialize(), "interface_detach", payload)
    tree = etree.parse(BytesIO(extracted))
    assert tree.getroot().get("type") == "network"
