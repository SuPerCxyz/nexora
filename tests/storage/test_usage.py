import json
from datetime import UTC, datetime

import pytest

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.storage.usage import StoragePoolInUseError, StoragePoolUsageGuard


@pytest.mark.parametrize(
    "disk",
    [
        {"source": "/var/lib/libvirt/images/vm.qcow2", "pool": None},
        {"source": "vm.qcow2", "pool": "images"},
    ],
)
def test_pool_usage_guard_blocks_file_and_volume_references(
    settings: Settings,
    disk: dict[str, object],
) -> None:
    database = Database(settings)
    upgrade_database(database)
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
        session.add(
            ResourceIndex(
                id="vm-1",
                host_id="host-1",
                resource_type=ResourceType.VIRTUAL_MACHINE,
                native_id="11111111-1111-1111-1111-111111111111",
                display_name="important-vm",
                status=ResourceStatus.MANAGED,
                source="existing",
                observed_generation=1,
                details_json=json.dumps({"disks": [disk]}),
                labels_json="[]",
                first_seen_at=now,
                last_seen_at=now,
            )
        )

    with pytest.raises(StoragePoolInUseError, match="important-vm"):
        StoragePoolUsageGuard(database).ensure_not_in_use(
            "host-1",
            "images",
            "/var/lib/libvirt/images",
        )
    database.dispose()


def test_volume_reference_reports_vm_state(settings: Settings) -> None:
    database = Database(settings)
    upgrade_database(database)
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
        session.add(
            ResourceIndex(
                id="vm-1",
                host_id="host-1",
                resource_type=ResourceType.VIRTUAL_MACHINE,
                native_id="11111111-1111-1111-1111-111111111111",
                display_name="running-vm",
                status=ResourceStatus.MANAGED,
                source="existing",
                observed_generation=1,
                details_json=json.dumps(
                    {
                        "state": "running",
                        "disks": [{"source": "vm.qcow2", "pool": "images"}],
                    }
                ),
                labels_json="[]",
                first_seen_at=now,
                last_seen_at=now,
            )
        )

    references = StoragePoolUsageGuard(database).volume_references(
        "host-1",
        pool_name="images",
        volume_name="vm.qcow2",
        volume_key="/images/vm.qcow2",
        volume_path="/images/vm.qcow2",
    )

    assert 1 == len(references)
    assert references[0].active
    assert "running-vm" == references[0].vm_name
    database.dispose()
