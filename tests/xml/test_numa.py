"""Tests for NUMA cell write operations."""

import pytest

from nexora.xml import LibvirtXmlDocument, NumaCellChange, NumaChange, NumaConfigError
from nexora.xml.numa import apply_numa_change, read_numa_config

DOMAIN_NO_NUMA = b"""<domain type="kvm">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">4194304</memory>
  <vcpu>4</vcpu>
  <cpu mode="host-passthrough"/>
  <devices></devices>
</domain>"""

DOMAIN_WITH_NUMA = b"""<domain type="kvm">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">4194304</memory>
  <vcpu>4</vcpu>
  <cpu mode="host-passthrough">
    <vendor:custom xmlns:vendor="urn:vendor" flag="keep"/>
    <numa>
      <cell id="0" cpus="0-1" memory="2097152" unit="KiB" memAccess="shared"/>
      <cell id="1" cpus="2-3" memory="2097152" unit="KiB"/>
    </numa>
  </cpu>
  <devices></devices>
</domain>"""


def _parse(xml: bytes):
    return LibvirtXmlDocument.parse(xml, expected_root="domain")


def test_read_numa_from_empty_domain() -> None:
    config = read_numa_config(_parse(DOMAIN_NO_NUMA))
    assert config == []


def test_read_numa_config() -> None:
    config = read_numa_config(_parse(DOMAIN_WITH_NUMA))
    assert len(config) == 2
    assert config[0].cell_id == 0
    assert config[0].cpus == "0-1"
    assert config[0].memory_kib == 2097152
    assert config[0].mem_access == "shared"
    assert config[1].cell_id == 1
    assert config[1].mem_access is None


def test_apply_numa_creates_section() -> None:
    doc = _parse(DOMAIN_NO_NUMA)
    change = NumaChange(
        cells=[
            NumaCellChange(0, "0-1", 2097152, "shared"),
            NumaCellChange(1, "2-3", 2097152),
        ]
    )
    apply_numa_change(doc, change, max_vcpus=4, memory_kib=4194304)
    cells = doc.root.findall("cpu/numa/cell")
    assert len(cells) == 2
    assert cells[0].get("cpus") == "0-1"
    assert cells[0].get("memAccess") == "shared"
    assert cells[1].get("memAccess") is None


def test_apply_numa_preserves_vendor_elements() -> None:
    doc = _parse(DOMAIN_WITH_NUMA)
    change = NumaChange(
        cells=[
            NumaCellChange(0, "0-3", 4194304),
        ]
    )
    apply_numa_change(doc, change, max_vcpus=4, memory_kib=4194304)
    vendor = doc.root.find("cpu/{urn:vendor}custom")
    assert vendor is not None
    assert vendor.get("flag") == "keep"


def test_apply_numa_clears_section_when_empty() -> None:
    doc = _parse(DOMAIN_WITH_NUMA)
    change = NumaChange(cells=[])
    apply_numa_change(doc, change, max_vcpus=4, memory_kib=4194304)
    assert doc.root.find("cpu/numa") is None


def test_numa_validates_overlapping_cpus() -> None:
    change = NumaChange(
        cells=[
            NumaCellChange(0, "0-1", 2097152),
            NumaCellChange(1, "1-2", 2097152),
        ]
    )
    with pytest.raises(NumaConfigError, match="overlapping"):
        change.validate(max_vcpus=4, memory_kib=4194304)


def test_numa_validates_vcpu_range() -> None:
    change = NumaChange(
        cells=[
            NumaCellChange(0, "0-5", 4194304),
        ]
    )
    with pytest.raises(NumaConfigError, match="vCPU"):
        change.validate(max_vcpus=4, memory_kib=4194304)


def test_numa_validates_memory_exceeds_domain() -> None:
    change = NumaChange(
        cells=[
            NumaCellChange(0, "0-1", 8388608),
        ]
    )
    with pytest.raises(NumaConfigError, match="exceeds domain memory"):
        change.validate(max_vcpus=4, memory_kib=4194304)


def test_numa_validates_duplicate_cell_ids() -> None:
    change = NumaChange(
        cells=[
            NumaCellChange(0, "0-1", 2097152),
            NumaCellChange(0, "2-3", 2097152),
        ]
    )
    with pytest.raises(NumaConfigError, match="unique"):
        change.validate(max_vcpus=4, memory_kib=4194304)


def test_numa_validates_invalid_cpus_format() -> None:
    with pytest.raises(NumaConfigError, match="cpus format"):
        NumaCellChange(0, "abc", 1024).validate()


def test_numa_validates_invalid_mem_access() -> None:
    with pytest.raises(NumaConfigError, match="memAccess"):
        NumaCellChange(0, "0", 1024, "unknown").validate()
