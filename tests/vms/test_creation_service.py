import json
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy.orm import Session

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.creation_authority import VerifiedImportVolume
from nexora.vms.creation_contracts import VmImportCreateInput
from nexora.vms.creation_models import VmCreationPlan
from nexora.vms.creation_service import VmCreationService

VM_UUID = "22222222-2222-2222-2222-222222222222"
POOL_UUID = "11111111-1111-1111-1111-111111111111"
VOLUME_NATIVE = '["11111111-1111-1111-1111-111111111111","/images/system.qcow2"]'


class Authority:
    def refresh_and_verify(self, _create: VmImportCreateInput) -> VerifiedImportVolume:
        return VerifiedImportVolume("/images/system.qcow2", "qcow2", "x86_64", None, None)


class Remote:
    def __init__(self) -> None:
        self.defined = False

    def validate_xml(self, _host_id: str, content: bytes) -> None:
        assert b"/images/system.qcow2" in content

    def define(self, _host_id: str, content: bytes) -> None:
        assert b"<name>created-vm</name>" in content
        self.defined = True


class Domains:
    def __init__(self, database: Database, remote: Remote) -> None:
        self.database = database
        self.remote = remote

    def run(self, host_id: str) -> None:
        if not self.remote.defined:
            return
        now = datetime.now(UTC)
        with self.database.session() as session:
            if session.get(ResourceIndex, "created-resource") is not None:
                return
            session.add(
                ResourceIndex(
                    id="created-resource",
                    host_id=host_id,
                    resource_type=ResourceType.VIRTUAL_MACHINE,
                    native_id=VM_UUID,
                    display_name="created-vm",
                    status=ResourceStatus.MANAGED,
                    source="nexora",
                    persistent_hash="c" * 64,
                    observed_generation=1,
                    details_json=json.dumps(
                        {
                            "persistent": True,
                            "state": "shut off",
                            "maximum_vcpus": 2,
                            "memory_kib": 2 * 1024 * 1024,
                            "disks": [
                                {
                                    "source": "/images/system.qcow2",
                                    "format": "qcow2",
                                    "target": "vda",
                                }
                            ],
                        }
                    ),
                    labels_json="[]",
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )


def test_creation_preview_confirm_execute_and_verify(settings: Settings) -> None:
    database = Database(settings)
    upgrade_database(database)
    _seed(database)
    remote = Remote()
    service = VmCreationService(
        database,
        Authority(),  # type: ignore[arg-type]
        remote,  # type: ignore[arg-type]
        Domains(database, remote),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        ResourceLockStore(database),
    )
    create = _create_input()

    preview = service.preview(create)
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=VM_UUID,
    )
    summary = service.execute(preview.plan.id, task_id="task-create")

    assert "state=shutoff" in summary
    assert remote.defined
    with database.session() as session:
        plan = session.get(VmCreationPlan, preview.plan.id)
        assert plan is not None
        assert VmChangePlanStatus.SUCCEEDED == plan.status
        assert "created-resource" == plan.result_resource_id
    database.dispose()


def _create_input() -> VmImportCreateInput:
    return VmImportCreateInput(
        host_id="host-1",
        pool_resource_id="pool-1",
        pool_uuid=POOL_UUID,
        pool_generation=1,
        pool_hash="a" * 64,
        volume_resource_id="volume-1",
        volume_native_id=VOLUME_NATIVE,
        volume_generation=1,
        volume_hash="b" * 64,
        volume_key="/images/system.qcow2",
        volume_name="system.qcow2",
        current_capacity_bytes=10 * 1024**3,
        name="created-vm",
        memory_mib=2048,
        vcpus=2,
        vm_uuid=VM_UUID,
    )


def _seed(database: Database) -> None:
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
        _add_storage(session, now)


def _add_storage(session: Session, now: datetime) -> None:
    common = {
        "host_id": "host-1",
        "status": ResourceStatus.MANAGED,
        "source": "existing",
        "observed_generation": 1,
        "labels_json": "[]",
        "first_seen_at": now,
        "last_seen_at": now,
    }
    session.add(
        ResourceIndex(
            id="pool-1",
            resource_type=ResourceType.STORAGE_POOL,
            native_id=POOL_UUID,
            display_name="images",
            persistent_hash="a" * 64,
            details_json=json.dumps({"pool_type": "dir", "active": True}),
            **common,
        )
    )
    session.add(
        ResourceIndex(
            id="volume-1",
            resource_type=ResourceType.STORAGE_VOLUME,
            native_id=VOLUME_NATIVE,
            parent_native_id=POOL_UUID,
            display_name="system.qcow2",
            persistent_hash="b" * 64,
            details_json=json.dumps(
                {
                    "key": "/images/system.qcow2",
                    "path": "/images/system.qcow2",
                    "format": "qcow2",
                    "capacity_bytes": 10 * 1024**3,
                }
            ),
            **common,
        )
    )
