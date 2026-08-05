"""Tests for CPU pinning (cputune) write operations."""

import pytest

from nexora.xml import (
    CpuTuneChange,
    CpuTuneError,
    EmulatorPinChange,
    LibvirtXmlDocument,
    VcpuPinChange,
)
from nexora.xml.cputune import apply_cputune_change, read_cputune

DOMAIN_NO_CPUTUNE = b"""<domain type="kvm">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">2097152</memory>
  <vcpu>4</vcpu>
  <devices></devices>
</domain>"""

DOMAIN_WITH_CPUTUNE = b"""<domain type="kvm">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">2097152</memory>
  <vcpu>4</vcpu>
  <cputune>
    <vcpupin vcpu="0" cpuset="0"/>
    <vcpupin vcpu="1" cpuset="1"/>
    <emulatorpin cpuset="0-3"/>
  </cputune>
  <devices></devices>
</domain>"""


def _parse(xml: bytes):
    return LibvirtXmlDocument.parse(xml, expected_root="domain")


def test_read_cputune_from_empty_domain() -> None:
    config = read_cputune(_parse(DOMAIN_NO_CPUTUNE))
    assert config.vcpu_pins == []
    assert config.emulator_pin is None


def test_read_cputune_config() -> None:
    config = read_cputune(_parse(DOMAIN_WITH_CPUTUNE))
    assert len(config.vcpu_pins) == 2
    assert config.vcpu_pins[0].vcpu_id == 0
    assert config.vcpu_pins[0].cpuset == "0"
    assert config.emulator_pin is not None
    assert config.emulator_pin.cpuset == "0-3"


def test_apply_cputune_creates_section() -> None:
    doc = _parse(DOMAIN_NO_CPUTUNE)
    change = CpuTuneChange(
        vcpu_pins=[
            VcpuPinChange(0, "0"),
            VcpuPinChange(1, "1"),
        ],
        emulator_pin=EmulatorPinChange("0-1"),
    )
    apply_cputune_change(doc, change, max_vcpus=4)
    cputune = doc.root.find("cputune")
    assert cputune is not None
    pins = cputune.findall("vcpupin")
    assert len(pins) == 2
    assert pins[0].get("vcpu") == "0"
    assert pins[0].get("cpuset") == "0"
    emulator = cputune.find("emulatorpin")
    assert emulator is not None
    assert emulator.get("cpuset") == "0-1"


def test_apply_cputune_replaces_existing() -> None:
    doc = _parse(DOMAIN_WITH_CPUTUNE)
    change = CpuTuneChange(
        vcpu_pins=[VcpuPinChange(2, "2,4")],
    )
    apply_cputune_change(doc, change, max_vcpus=4)
    cputune = doc.root.find("cputune")
    pins = cputune.findall("vcpupin")
    assert len(pins) == 1
    assert pins[0].get("vcpu") == "2"
    assert cputune.find("emulatorpin") is None


def test_apply_cputune_clears_when_empty() -> None:
    doc = _parse(DOMAIN_WITH_CPUTUNE)
    change = CpuTuneChange(vcpu_pins=[])
    apply_cputune_change(doc, change, max_vcpus=4)
    assert doc.root.find("cputune") is None


def test_cputune_validates_vcpu_range() -> None:
    change = CpuTuneChange(vcpu_pins=[VcpuPinChange(10, "0")])
    with pytest.raises(CpuTuneError, match="exceeds"):
        change.validate(max_vcpus=4)


def test_cputune_validates_duplicate_vcpu() -> None:
    change = CpuTuneChange(
        vcpu_pins=[
            VcpuPinChange(0, "0"),
            VcpuPinChange(0, "1"),
        ]
    )
    with pytest.raises(CpuTuneError, match="duplicate"):
        change.validate(max_vcpus=4)


def test_cputune_validates_invalid_cpuset() -> None:
    with pytest.raises(CpuTuneError, match="cpuset format"):
        VcpuPinChange(0, "abc").validate()


def test_cputune_supports_ranges() -> None:
    doc = _parse(DOMAIN_NO_CPUTUNE)
    change = CpuTuneChange(
        vcpu_pins=[
            VcpuPinChange(0, "0-1"),
            VcpuPinChange(1, "2,3"),
        ]
    )
    apply_cputune_change(doc, change, max_vcpus=4)
    cputune = doc.root.find("cputune")
    pins = cputune.findall("vcpupin")
    assert pins[0].get("cpuset") == "0-1"
    assert pins[1].get("cpuset") == "2,3"
