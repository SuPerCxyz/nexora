from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import func, select

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.remote.executor import RemoteCommandAudit, RemoteExecutor
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile
from nexora.resources.libvirt_network_discovery import LibvirtNetworkDiscoveryService
from nexora.resources.models import ResourceIndex
from nexora.resources.node_device_discovery import NodeDeviceDiscoveryService
from nexora.resources.storage_discovery import StorageDiscoveryService

UUID = "11111111-1111-1111-1111-111111111111"


class Resolver:
    def __init__(self, known_hosts: Path) -> None:
        self.known_hosts = known_hosts

    def resolve(self, _host_id: str) -> SSHConnectionProfile:
        return SSHConnectionProfile(SSHConnection("node", 22, "root", self.known_hosts))


class Audit:
    def record(self, _event: RemoteCommandAudit) -> None:
        return


class ResourceBackend:
    def run(
        self,
        _profile: SSHConnectionProfile,
        command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult:
        del timeout, stdin, cancel_event
        return _result(_output(command))


class UnreadableVolumeBackend:
    """One volume lists but its vol-dumpxml query fails."""

    def run(
        self,
        _profile: SSHConnectionProfile,
        command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult:
        del timeout, stdin, cancel_event
        if "pool-list --all --name" in command:
            return _result(b"default\n")
        if "pool-info default" in command:
            return _result(b"State: running\nPersistent: yes\nAutostart: yes\n")
        if "pool-dumpxml default" in command:
            return _result(_pool_xml())
        if "vol-list" in command:
            return _result(
                b" Name     Path\n----------------------\n"
                b" ok.qcow2 /images/ok.qcow2\n"
                b" bad.md   /root/tmp/bad.md\n"
            )
        if "vol-dumpxml ok.qcow2" in command:
            return _result(_volume_xml())
        if "vol-dumpxml bad.md" in command:
            return ProcessResult(
                1, b"", b"error: volume not found", False, False, False, False, 0.01
            )
        raise AssertionError(command)


@pytest.fixture
def services(
    settings: Settings,
) -> Iterator[
    tuple[
        Database,
        StorageDiscoveryService,
        LibvirtNetworkDiscoveryService,
        NodeDeviceDiscoveryService,
    ]
]:
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    executor = RemoteExecutor(
        Resolver(settings.data_dir / "hostkeys" / "known_hosts"),
        Audit(),
        backend=ResourceBackend(),
    )
    try:
        yield (
            database,
            StorageDiscoveryService(database, executor),
            LibvirtNetworkDiscoveryService(database, executor),
            NodeDeviceDiscoveryService(database, executor),
        )
    finally:
        database.dispose()


def test_nonempty_storage_network_and_devices_are_indexed(
    services: tuple[
        Database,
        StorageDiscoveryService,
        LibvirtNetworkDiscoveryService,
        NodeDeviceDiscoveryService,
    ],
) -> None:
    database, storage, networks, devices = services

    storage_result = storage.run("host-1")
    network_result = networks.run("host-1")
    device_result = devices.run("host-1")

    assert 1 == len(storage_result.pools.resources)
    assert 1 == len(storage_result.volumes.resources)
    assert 1 == len(network_result.resources)
    assert 1 == len(device_result.pci.resources)
    assert 1 == len(device_result.usb.resources)
    with database.session() as session:
        assert 5 == session.scalar(select(func.count()).select_from(ResourceIndex))


def test_read_pool_refreshes_one_authoritative_pool(
    services: tuple[
        Database,
        StorageDiscoveryService,
        LibvirtNetworkDiscoveryService,
        NodeDeviceDiscoveryService,
    ],
) -> None:
    _database, storage, _networks, _devices = services

    observation = storage.read_pool("host-1", UUID)

    assert UUID == observation.native_id
    assert "/images" == observation.details["target_path"]


def test_storage_discovery_skips_unreadable_volume_and_reports_warning(
    settings: Settings,
) -> None:
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    executor = RemoteExecutor(
        Resolver(settings.data_dir / "hostkeys" / "known_hosts"),
        Audit(),
        backend=UnreadableVolumeBackend(),
    )
    discovery = StorageDiscoveryService(database, executor)
    try:
        result = discovery.run("host-1")
    finally:
        database.dispose()

    assert 1 == len(result.volumes.resources)
    assert "disk.qcow2" == result.volumes.resources[0].display_name
    assert 1 == len(result.warnings)
    assert "bad.md" in result.warnings[0]


def _output(command: str) -> bytes:
    if "pool-list --all --name" in command:
        return b"default\n"
    if "pool-info default" in command:
        return b"State: running\nPersistent: yes\nAutostart: yes\n"
    if "pool-dumpxml default" in command:
        return _pool_xml()
    if f"pool-info {UUID}" in command:
        return b"State: running\nPersistent: yes\nAutostart: yes\n"
    if f"pool-dumpxml {UUID}" in command:
        return _pool_xml()
    if f"vol-list {UUID}" in command:
        return b" Name       Path\n--------------------------\n disk.qcow2 /images/disk.qcow2\n"
    if "vol-dumpxml disk.qcow2" in command:
        return _volume_xml()
    if "net-list --all --uuid" in command:
        return f"{UUID}\n".encode()
    if f"net-info {UUID}" in command:
        return b"Active: yes\nPersistent: yes\nAutostart: yes\n"
    if f"net-dumpxml {UUID}" in command:
        return _network_xml()
    if "nodedev-list --cap pci" in command:
        return b"pci_0000_03_00_0\n"
    if "nodedev-list --cap usb_device" in command:
        return b"usb_1_2\n"
    if "nodedev-dumpxml pci_0000_03_00_0" in command:
        return _pci_xml()
    if "nodedev-dumpxml usb_1_2" in command:
        return _usb_xml()
    raise AssertionError(command)


def _pool_xml() -> bytes:
    return (
        f"<pool type='dir'><name>default</name><uuid>{UUID}</uuid>"
        "<capacity unit='bytes'>1000</capacity><allocation unit='bytes'>100</allocation>"
        "<available unit='bytes'>900</available><target><path>/images</path></target></pool>"
    ).encode()


def _volume_xml() -> bytes:
    return b"""\
<volume type="file"><name>disk.qcow2</name><key>/images/disk.qcow2</key>
<capacity unit="bytes">100</capacity><allocation unit="bytes">50</allocation>
<target><path>/images/disk.qcow2</path><format type="qcow2"/></target></volume>"""


def _network_xml() -> bytes:
    return (
        f"<network><name>default</name><uuid>{UUID}</uuid><forward mode='nat'/>"
        "<bridge name='virbr0'/></network>"
    ).encode()


def _pci_xml() -> bytes:
    return b"""\
<device><name>pci_0000_03_00_0</name><capability type="pci"><domain>0</domain>
<bus>3</bus><slot>0</slot><function>0</function></capability></device>"""


def _usb_xml() -> bytes:
    return b"""\
<device><name>usb_1_2</name><capability type="usb_device"><bus>1</bus>
<device>2</device><vendor id="0x1234"/><product id="0xabcd"/></capability></device>"""


def _add_host(database: Database) -> None:
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(
            Host(
                id="host-1",
                name="node",
                address="node.example.test",
                ssh_port=22,
                ssh_username="root",
                authentication_method=AuthenticationMethod.PRIVATE_KEY,
                sudo_mode=SudoMode.NONE,
                libvirt_uri="qemu:///system",
                status=HostStatus.READY,
                labels_json="[]",
                created_at=now,
                updated_at=now,
            )
        )


def _result(stdout: bytes) -> ProcessResult:
    return ProcessResult(0, stdout, b"", False, False, False, False, 0.01)
