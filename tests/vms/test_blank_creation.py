import json
from datetime import UTC, datetime
from types import SimpleNamespace

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.blank_creation_authority import VerifiedBlankDisk
from nexora.vms.blank_creation_contracts import VmBlankCreateInput
from nexora.vms.blank_creation_models import VmBlankCreationPlan
from nexora.vms.blank_creation_service import VmBlankCreationService
from nexora.vms.change_models import VmChangePlanStatus

VM_UUID = "22222222-2222-2222-2222-222222222222"
POOL_UUID = "11111111-1111-1111-1111-111111111111"


class Remote:
    def __init__(self) -> None:
        self.defined = False

    def validate_xml(self, _host_id: str, content: bytes) -> None:
        assert b"/images/blank.qcow2" in content

    def define(self, _host_id: str, content: bytes) -> None:
        assert b"<name>blank-vm</name>" in content
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
                    display_name="blank-vm",
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
                                    "source": "/images/blank.qcow2",
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


class Remote:
    def __init__(self) -> None:
        self.defined = False

    def validate_xml(self, _host_id: str, content: bytes) -> None:
        assert b"/images/blank.qcow2" in content

    def define(self, _host_id: str, content: bytes) -> None:
        assert b"<name>blank-vm</name>" in content
        self.defined = True


class VolumeCommands:
    def __init__(self) -> None:
        self.created = False

    def validate_xml(self, _host_id: str, content: bytes) -> None:
        assert b"blank.qcow2" in content

    def virsh(self, host_id: str, arguments: tuple[str, ...], *, stdin: bytes | None = None):
        assert arguments[:2] == ("vol-create", POOL_UUID)
        self.created = True
        return SimpleNamespace(
            exit_code=0,
            timed_out=False,
            cancelled=False,
            stdout_truncated=False,
            stderr_truncated=False,
            stdout="",
            stderr="",
        )


class Storage:
    def __init__(self, database: Database, volume_commands: VolumeCommands) -> None:
        self.database = database
        self.volume_commands = volume_commands

    def run(self, host_id: str) -> None:
        if not self.volume_commands.created:
            return
        now = datetime.now(UTC)
        with self.database.session() as session:
            if session.get(ResourceIndex, "blank-volume-resource") is not None:
                return
            session.add(
                ResourceIndex(
                    id="blank-volume-resource",
                    host_id=host_id,
                    resource_type=ResourceType.STORAGE_VOLUME,
                    native_id=json.dumps([POOL_UUID, "/images/blank.qcow2"]),
                    parent_native_id=POOL_UUID,
                    display_name="blank.qcow2",
                    status=ResourceStatus.MANAGED,
                    source="nexora",
                    persistent_hash="e" * 64,
                    observed_generation=1,
                    details_json=json.dumps(
                        {
                            "key": "/images/blank.qcow2",
                            "path": "/images/blank.qcow2",
                            "format": "qcow2",
                            "capacity_bytes": 20 * 1024**3,
                        }
                    ),
                    labels_json="[]",
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )


class Authority:
    def __init__(self, database: Database, remote: Remote, volume_commands: VolumeCommands) -> None:
        self.database = database
        self.remote = remote
        self.volume_commands = volume_commands
        self.storage = Storage(database, volume_commands)
        self.options = SimpleNamespace(domains=Domains(database, remote))

    def refresh_and_verify(self, _create: VmBlankCreateInput) -> VerifiedBlankDisk:
        return VerifiedBlankDisk("/images/blank.qcow2", "qcow2", "x86_64", None, None)


def test_blank_creation_preview_confirm_execute_and_verify(settings: Settings) -> None:
    database = Database(settings)
    upgrade_database(database)
    _seed(database)
    remote = Remote()
    volume_commands = VolumeCommands()
    authority = Authority(database, remote, volume_commands)
    service = VmBlankCreationService(
        database,
        authority,  # type: ignore[arg-type]
        remote,  # type: ignore[arg-type]
        volume_commands,  # type: ignore[arg-type]
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
    summary = service.execute(preview.plan.id, task_id="task-blank")

    assert "state=shutoff" in summary
    assert remote.defined
    assert volume_commands.created
    with database.session() as session:
        plan = session.get(VmBlankCreationPlan, preview.plan.id)
        assert plan is not None
        assert VmChangePlanStatus.SUCCEEDED == plan.status
        assert "created-resource" == plan.result_resource_id
    database.dispose()


def _create_input() -> VmBlankCreateInput:
    return VmBlankCreateInput(
        host_id="host-1",
        pool_resource_id="pool-1",
        pool_uuid=POOL_UUID,
        pool_generation=1,
        pool_hash="a" * 64,
        disk_name="blank.qcow2",
        volume_format="qcow2",
        capacity_bytes=20 * 1024**3,
        name="blank-vm",
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
        session.add(
            ResourceIndex(
                id="pool-1",
                host_id="host-1",
                resource_type=ResourceType.STORAGE_POOL,
                native_id=POOL_UUID,
                display_name="images",
                status=ResourceStatus.MANAGED,
                source="existing",
                persistent_hash="a" * 64,
                observed_generation=1,
                details_json=json.dumps(
                    {"pool_type": "dir", "active": True, "target_path": "/images"}
                ),
                labels_json="[]",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
