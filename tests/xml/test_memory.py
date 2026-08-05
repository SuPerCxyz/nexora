import pytest

from nexora.xml import LibvirtXmlDocument, MemoryConfigChange
from nexora.xml.diff import xml_diff
from nexora.xml.errors import XmlStructureError
from nexora.xml.memory import apply_memory_config, read_memory_config

DOMAIN_XML = b"""<domain type="kvm" xmlns:vendor="urn:vendor">
  <name>guest</name>
  <memory unit="MiB" vendor:hint="keep">4096</memory>
  <currentMemory unit="MiB">2048</currentMemory>
  <memoryBacking vendor:policy="keep">
    <hugepages><page size="1" unit="G" nodeset="0"/></hugepages>
    <source type="memfd"/>
    <access mode="shared"/>
    <vendor:extension enabled="yes"/>
  </memoryBacking>
  <vcpu>4</vcpu>
  <devices/>
</domain>"""


def test_memory_change_preserves_unknown_elements_and_attributes() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN_XML)
    change = MemoryConfigChange(
        current_kib=3 * 1024 * 1024,
        maximum_kib=8 * 1024 * 1024,
        hugepages=True,
        locked=True,
        source_type="memfd",
        access_mode="shared",
        allocation_mode="immediate",
        discard=True,
    )

    apply_memory_config(document, change)

    root = document.root
    backing = root.find("memoryBacking")
    assert backing is not None
    assert str(8 * 1024 * 1024) == root.findtext("memory")
    assert "keep" == root.find("memory").get("{urn:vendor}hint")  # type: ignore[union-attr]
    assert backing.find("hugepages/page") is not None
    assert backing.find("{urn:vendor}extension") is not None
    assert "keep" == backing.get("{urn:vendor}policy")
    assert backing.find("locked") is not None
    assert backing.find("discard") is not None


def test_memory_read_normalizes_units_and_diff_is_narrow() -> None:
    current = LibvirtXmlDocument.parse(DOMAIN_XML)
    proposed = LibvirtXmlDocument.parse(DOMAIN_XML)
    observed = read_memory_config(current)

    assert 2 * 1024 * 1024 == observed.current_kib
    assert 4 * 1024 * 1024 == observed.maximum_kib
    apply_memory_config(proposed, observed)
    rendered = xml_diff(current, proposed)
    assert "4194304" in rendered
    assert "2097152" in rendered
    assert "vendor:extension" not in rendered


def test_memory_change_validates_limits_and_modes() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN_XML)

    with pytest.raises(XmlStructureError, match="exceeds"):
        apply_memory_config(document, MemoryConfigChange(2048, 1024))
    with pytest.raises(XmlStructureError, match="source"):
        apply_memory_config(
            document,
            MemoryConfigChange(1024, 2048, source_type="untrusted"),
        )
