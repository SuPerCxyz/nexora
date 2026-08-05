"""Tests for read-only advanced libvirt domain XML configuration parsing."""

import pytest

from nexora.xml import LibvirtXmlDocument, read_advanced_config
from nexora.xml.errors import XmlStructureError

DOMAIN_NO_ADVANCED = b"""<domain type="kvm">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">2097152</memory>
  <vcpu>2</vcpu>
  <devices></devices>
</domain>"""

DOMAIN_WITH_NUMA = b"""<domain type="kvm">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">4194304</memory>
  <vcpu>4</vcpu>
  <cpu mode="host-passthrough">
    <numa>
      <cell id="0" cpus="0-1" memory="2097152" unit="KiB" memAccess="shared">
        <distances>
          <sibling id="0" value="10"/>
          <sibling id="1" value="20"/>
        </distances>
      </cell>
      <cell id="1" cpus="2-3" memory="2097152" unit="KiB" memAccess="private">
        <distances>
          <sibling id="0" value="20"/>
          <sibling id="1" value="10"/>
        </distances>
      </cell>
    </numa>
  </cpu>
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
    <vcpupin vcpu="2" cpuset="2,4"/>
    <vcpupin vcpu="3" cpuset="3,5"/>
    <emulatorpin cpuset="0-3"/>
  </cputune>
  <devices></devices>
</domain>"""

DOMAIN_WITH_WATCHDOG = b"""<domain type="kvm">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">2097152</memory>
  <vcpu>2</vcpu>
  <devices>
    <watchdog model="i6300esb" action="reset"/>
  </devices>
</domain>"""

DOMAIN_WITH_VSOCK = b"""<domain type="kvm">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">2097152</memory>
  <vcpu>2</vcpu>
  <devices>
    <vsock model="virtio">
      <cid auto="no" address="3"/>
    </vsock>
  </devices>
</domain>"""

DOMAIN_WITH_VSOCK_AUTO = b"""<domain type="kvm">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">2097152</memory>
  <vcpu>2</vcpu>
  <devices>
    <vsock model="virtio">
      <cid auto="yes"/>
    </vsock>
  </devices>
</domain>"""

DOMAIN_WITH_ALL = b"""<domain type="kvm">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">4194304</memory>
  <vcpu>4</vcpu>
  <cpu mode="host-passthrough">
    <numa>
      <cell id="0" cpus="0-1" memory="2097152" unit="KiB" memAccess="shared"/>
      <cell id="1" cpus="2-3" memory="2097152" unit="KiB"/>
    </numa>
  </cpu>
  <cputune>
    <vcpupin vcpu="0" cpuset="0"/>
    <emulatorpin cpuset="0-3"/>
  </cputune>
  <devices>
    <watchdog model="i6300esb" action="poweroff"/>
    <vsock model="virtio">
      <cid auto="no" address="7"/>
    </vsock>
  </devices>
</domain>"""

DOMAIN_WITH_VENDORS = b"""<domain type="kvm" xmlns:vendor="urn:vendor">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">2097152</memory>
  <vcpu>2</vcpu>
  <cpu mode="host-passthrough">
    <vendor:custom flag="keep"/>
    <numa>
      <cell id="0" cpus="0-1" memory="2097152" unit="KiB"/>
    </numa>
  </cpu>
  <devices>
    <watchdog model="diag288" action="none" vendor:tag="keep"/>
  </devices>
</domain>"""


def _parse(xml: bytes):
    return LibvirtXmlDocument.parse(xml, expected_root="domain")


def test_no_advanced_config_returns_empty() -> None:
    config = read_advanced_config(_parse(DOMAIN_NO_ADVANCED))
    assert config.numa_cells == []
    assert config.cpu_pinning == []
    assert config.watchdog is None
    assert config.vsock is None
    assert config.has_any is False


def test_numa_cells_parsed_correctly() -> None:
    config = read_advanced_config(_parse(DOMAIN_WITH_NUMA))
    assert len(config.numa_cells) == 2
    cell0 = config.numa_cells[0]
    assert cell0.cell_id == 0
    assert cell0.cpus == "0-1"
    assert cell0.memory_kib == 2097152
    assert cell0.mem_access == "shared"
    assert cell0.distances == [(0, 10), (1, 20)]
    cell1 = config.numa_cells[1]
    assert cell1.cell_id == 1
    assert cell1.mem_access == "private"
    assert cell1.distances == [(0, 20), (1, 10)]
    assert config.has_any is True


def test_numa_cell_without_distances() -> None:
    xml = b"""<domain type="kvm">
  <name>guest</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <vcpu>2</vcpu>
  <cpu><numa><cell id="0" cpus="0-1" memory="1048576" unit="KiB"/></numa></cpu>
  <devices></devices>
</domain>"""
    config = read_advanced_config(_parse(xml))
    assert len(config.numa_cells) == 1
    assert config.numa_cells[0].distances == []


def test_cpu_pinning_parsed_correctly() -> None:
    config = read_advanced_config(_parse(DOMAIN_WITH_CPUTUNE))
    assert len(config.cpu_pinning) == 5
    assert config.cpu_pinning[0].vcpu_id == 0
    assert config.cpu_pinning[0].cpuset == "0"
    assert config.cpu_pinning[0].emulator is False
    assert config.cpu_pinning[2].cpuset == "2,4"
    emulator = config.cpu_pinning[-1]
    assert emulator.emulator is True
    assert emulator.vcpu_id is None
    assert emulator.cpuset == "0-3"
    assert config.has_any is True


def test_watchdog_parsed_correctly() -> None:
    config = read_advanced_config(_parse(DOMAIN_WITH_WATCHDOG))
    assert config.watchdog is not None
    assert config.watchdog.model == "i6300esb"
    assert config.watchdog.action == "reset"
    assert config.has_any is True


def test_vsock_with_explicit_cid() -> None:
    config = read_advanced_config(_parse(DOMAIN_WITH_VSOCK))
    assert config.vsock is not None
    assert config.vsock.auto_cid is False
    assert config.vsock.cid == 3
    assert config.has_any is True


def test_vsock_with_auto_cid() -> None:
    config = read_advanced_config(_parse(DOMAIN_WITH_VSOCK_AUTO))
    assert config.vsock is not None
    assert config.vsock.auto_cid is True
    assert config.vsock.cid is None


def test_all_advanced_config_parsed_together() -> None:
    config = read_advanced_config(_parse(DOMAIN_WITH_ALL))
    assert len(config.numa_cells) == 2
    assert len(config.cpu_pinning) == 2
    assert config.watchdog is not None
    assert config.watchdog.model == "i6300esb"
    assert config.vsock is not None
    assert config.vsock.cid == 7
    assert config.has_any is True


def test_vendor_extension_elements_preserved() -> None:
    config = read_advanced_config(_parse(DOMAIN_WITH_VENDORS))
    assert len(config.numa_cells) == 1
    assert config.watchdog is not None
    assert config.watchdog.model == "diag288"
    root = _parse(DOMAIN_WITH_VENDORS).root
    vendor_tag = root.find("cpu/{urn:vendor}custom")
    assert vendor_tag is not None
    assert vendor_tag.get("flag") == "keep"


def test_non_domain_root_raises() -> None:
    xml = b"""<network><name>br0</name></network>"""
    with pytest.raises(XmlStructureError):
        read_advanced_config(LibvirtXmlDocument.parse(xml))
