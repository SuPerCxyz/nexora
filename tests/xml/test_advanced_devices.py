import pytest

from nexora.xml import (
    AdvancedDeviceChange,
    AdvancedDeviceError,
    LibvirtXmlDocument,
    apply_advanced_device_change,
)

DOMAIN = b"""<domain type="kvm" xmlns:vendor="urn:vendor">
  <name>guest</name><vcpu>2</vcpu>
  <cpu mode="host-passthrough"><vendor:keep value="yes"/><cache mode="disable"/></cpu>
  <devices><watchdog model="i6300esb" action="reset"/><vendor:device/></devices>
</domain>"""


def test_advanced_devices_replace_only_owned_elements() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")

    apply_advanced_device_change(
        document,
        AdvancedDeviceChange(
            watchdog_model="ib700",
            watchdog_action="poweroff",
            vsock_mode="explicit",
            vsock_cid=7,
            cache_mode="passthrough",
            maxphysaddr_mode="emulate",
            maxphysaddr_bits=48,
        ),
    )

    assert document.root.find("./devices/watchdog").get("model") == "ib700"
    assert document.root.find("./devices/vsock/cid").get("address") == "7"
    assert document.root.find("./cpu/cache").get("mode") == "passthrough"
    assert document.root.find("./cpu/maxphysaddr").get("bits") == "48"
    assert document.root.find("./cpu/{urn:vendor}keep") is not None
    assert document.root.find("./devices/{urn:vendor}device") is not None


def test_advanced_devices_accept_libvirt_itco_watchdog() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    apply_advanced_device_change(
        document,
        AdvancedDeviceChange(watchdog_model="itco", watchdog_action="reset"),
    )
    watchdog = document.root.find("./devices/watchdog")
    assert watchdog is not None
    assert watchdog.get("model") == "itco"
    assert watchdog.get("action") == "reset"


def test_advanced_devices_keep_unchanged_watchdog_in_place() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    apply_advanced_device_change(
        document,
        AdvancedDeviceChange(watchdog_model="i6300esb", watchdog_action="reset"),
    )
    devices = document.root.find("./devices")
    assert devices is not None
    watchdog_positions = [index for index, item in enumerate(devices) if item.tag == "watchdog"]
    assert watchdog_positions == [0]
    watchdog = devices.find("watchdog")
    assert watchdog is not None
    assert watchdog.get("model") == "i6300esb"
    assert watchdog.get("action") == "reset"


def test_advanced_devices_support_explicit_removal() -> None:
    document = LibvirtXmlDocument.parse(DOMAIN, expected_root="domain")
    apply_advanced_device_change(document, AdvancedDeviceChange())
    assert document.root.find("./devices/watchdog") is None
    assert document.root.find("./devices/vsock") is None
    assert document.root.find("./cpu/cache") is None


@pytest.mark.parametrize(
    "change",
    [
        AdvancedDeviceChange(watchdog_model="unknown", watchdog_action="reset"),
        AdvancedDeviceChange(vsock_mode="explicit", vsock_cid=2),
        AdvancedDeviceChange(maxphysaddr_mode="passthrough", maxphysaddr_bits=48),
    ],
)
def test_advanced_devices_reject_invalid_inputs(change: AdvancedDeviceChange) -> None:
    with pytest.raises(AdvancedDeviceError):
        change.validate()
