import pytest
from lxml import etree

from nexora.xml import CpuTopologyChange, CpuTopologyError, LibvirtXmlDocument
from nexora.xml.cpu import apply_cpu_topology
from nexora.xml.diff import xml_diff

DOMAIN_XML = b"""<domain type="kvm" xmlns:vendor="urn:vendor">
  <name>guest</name>
  <metadata><vendor:policy mode="keep"/></metadata>
  <vcpu placement="static" vendor:hint="keep" current="2">4</vcpu>
  <cpu mode="host-passthrough" check="none" vendor:flag="keep">
    <model fallback="allow">custom-unknown</model>
    <topology sockets="1" dies="1" clusters="1" cores="2" threads="2"
              vendor:topology="keep"/>
    <vendor:extension enabled="yes"/>
  </cpu>
  <devices><vendor:device opaque="yes"/></devices>
</domain>"""


def _change() -> CpuTopologyChange:
    return CpuTopologyChange(
        current_vcpus=4,
        maximum_vcpus=8,
        sockets=1,
        dies=1,
        clusters=1,
        cores=4,
        threads=2,
    )


def test_cpu_change_preserves_unknown_elements_attributes_and_order() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN_XML, expected_root="domain")

    apply_cpu_topology(document, _change())

    root = document.root
    topology = root.find("cpu/topology")
    assert topology is not None
    assert "8" == root.findtext("vcpu")
    assert "4" == root.find("vcpu").get("current")  # type: ignore[union-attr]
    assert "4" == topology.get("cores")
    assert "keep" == topology.get("{urn:vendor}topology")
    assert "keep" == root.find("cpu").get("{urn:vendor}flag")  # type: ignore[union-attr]
    assert root.find("cpu/{urn:vendor}extension") is not None
    assert root.find("devices/{urn:vendor}device") is not None
    assert ["model", "topology", "extension"] == [
        etree.QName(child).localname
        for child in root.find("cpu")  # type: ignore[union-attr]
    ]


def test_cpu_change_produces_narrow_reviewable_diff() -> None:
    current = LibvirtXmlDocument.parse(DOMAIN_XML)
    proposed = LibvirtXmlDocument.parse(DOMAIN_XML)

    apply_cpu_topology(proposed, _change())
    rendered = xml_diff(current, proposed)

    assert 'current="2"' in rendered
    assert 'current="4"' in rendered
    assert '\n+    <vendor:extension enabled="yes"' not in rendered
    assert '\n-    <vendor:extension enabled="yes"' not in rendered


def test_cpu_topology_product_and_current_vcpu_are_validated() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN_XML)
    invalid_product = CpuTopologyChange(2, 8, 1, 1, 1, 2, 2)
    invalid_current = CpuTopologyChange(9, 8, 1, 1, 1, 4, 2)

    with pytest.raises(CpuTopologyError, match="product"):
        apply_cpu_topology(document, invalid_product)
    with pytest.raises(CpuTopologyError, match="current"):
        apply_cpu_topology(document, invalid_current)
