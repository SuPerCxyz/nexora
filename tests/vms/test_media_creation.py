import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.media.models import MediaItem, MediaStatus
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.media_creation_contracts import VmMediaCreateInput
from nexora.vms.media_creation_models import VmMediaCreationPlan
from nexora.vms.media_creation_service import VmMediaCreationService

VM_UUID = "22222222-2222-2222-2222-222222222222"
POOL_UUID = "11111111-1111-1111-1111-111111111111"
TARGET_PATH = "/images/copied.qcow2"


class Authority:
    def verify(self, _create: VmMediaCreateInput, *, task_id: str) -> object:
        assert task_id
        return SimpleNamespace(
            architecture="x86_64",
            disk_path=TARGET_PATH,
            iso_path=None,
            driver_iso_path=None,
            cloud_init_path=None,
        )


class Copier:
    def execute(self, _copy_input: object, **kwargs: object) -> str:
        progress = kwargs["progress"]
        progress(2, 50, "copied")  # type: ignore[operator]
        return "copied"


class Resize:
    def __init__(self) -> None:
        self.current: int | None = None
        self.digest = "f" * 64

    def virtual_size(self, _host_id: str, _path: str) -> int | None:
        return self.current

    def grow(
        self,
        _host_id: str,
        _path: str,
        expected: int,
        target: int,
    ) -> None:
        assert 1024 == expected
        assert 2048 == target
        self.current = target

    def sha256(self, _host_id: str, _path: str) -> str:
        return self.digest


class Remote:
    def __init__(self) -> None:
        self.defined = False

    def validate_xml(self, _host_id: str, content: bytes) -> None:
        assert TARGET_PATH.encode() in content

    def refresh_pool(self, _host_id: str, pool_uuid: str) -> None:
        assert POOL_UUID == pool_uuid

    def define(self, _host_id: str, _content: bytes) -> None:
        self.defined = True


class Storage:
    def __init__(self, database: Database) -> None:
        self.database = database

    def run(self, host_id: str) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            if session.get(ResourceIndex, "copied-volume") is not None:
                return
            session.add(
                ResourceIndex(
                    id="copied-volume",
                    host_id=host_id,
                    resource_type=ResourceType.STORAGE_VOLUME,
                    native_id=json.dumps([POOL_UUID, TARGET_PATH]),
                    parent_native_id=POOL_UUID,
                    display_name="copied.qcow2",
                    status=ResourceStatus.MANAGED,
                    source="existing",
                    persistent_hash="d" * 64,
                    observed_generation=1,
                    details_json=json.dumps(
                        {
                            "path": TARGET_PATH,
                            "format": "qcow2",
                            "backing_path": None,
                        }
                    ),
                    labels_json="[]",
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )


class Domains:
    def __init__(self, database: Database, remote: Remote) -> None:
        self.database = database
        self.remote = remote

    def run(self, host_id: str) -> None:
        if not self.remote.defined:
            return
        now = datetime.now(UTC)
        with self.database.session() as session:
            if session.get(ResourceIndex, "created-media-vm") is not None:
                return
            session.add(
                ResourceIndex(
                    id="created-media-vm",
                    host_id=host_id,
                    resource_type=ResourceType.VIRTUAL_MACHINE,
                    native_id=VM_UUID,
                    display_name="media-vm",
                    status=ResourceStatus.MANAGED,
                    source="nexora",
                    persistent_hash="e" * 64,
                    observed_generation=1,
                    details_json=json.dumps(
                        {
                            "persistent": True,
                            "state": "shut off",
                            "maximum_vcpus": 2,
                            "memory_kib": 2 * 1024 * 1024,
                            "disks": [
                                {
                                    "source": TARGET_PATH,
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


def test_media_creation_contract_round_trip_and_rejects_extension() -> None:
    create = _input()
    assert create == VmMediaCreateInput.decode(create.encode())
    invalid = VmMediaCreateInput(**{**vars(create), "target_file_name": "copied.raw"})
    with pytest.raises(ValueError, match="target identity"):
        invalid.validate()


def test_media_creation_preview_confirm_copy_define_and_verify(settings: Settings) -> None:
    database = Database(settings)
    upgrade_database(database)
    _seed(database)
    remote = Remote()
    service = VmMediaCreationService(
        database,
        Authority(),  # type: ignore[arg-type]
        Copier(),  # type: ignore[arg-type]
        remote,  # type: ignore[arg-type]
        Storage(database),  # type: ignore[arg-type]
        Domains(database, remote),  # type: ignore[arg-type]
        ResourceLockStore(database),
    )
    create = _input()
    preview = service.preview(create)
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=VM_UUID,
    )
    messages: list[str] = []
    summary = service.execute(
        preview.plan.id,
        task_id="task-media-create",
        progress=lambda _step, _percentage, message: messages.append(message),
    )
    assert "platform image" in summary
    assert remote.defined
    assert any("Copied" in message or "copied" in message for message in messages)
    with database.session() as session:
        plan = session.get(VmMediaCreationPlan, preview.plan.id)
        assert plan is not None
        assert VmChangePlanStatus.SUCCEEDED == plan.status
        assert "created-media-vm" == plan.result_resource_id
    database.dispose()


def test_media_creation_grows_copy_and_persists_recovery_hash(
    settings: Settings,
) -> None:
    database = Database(settings)
    upgrade_database(database)
    _seed(database)
    remote = Remote()
    resize = Resize()
    service = VmMediaCreationService(
        database,
        Authority(),  # type: ignore[arg-type]
        Copier(),  # type: ignore[arg-type]
        remote,  # type: ignore[arg-type]
        Storage(database),  # type: ignore[arg-type]
        Domains(database, remote),  # type: ignore[arg-type]
        ResourceLockStore(database),
        image_resize=resize,  # type: ignore[arg-type]
    )
    create = VmMediaCreateInput(
        **{
            **vars(_input()),
            "source_virtual_size_bytes": 1024,
            "target_capacity_bytes": 2048,
        }
    )
    preview = service.preview(create)
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=VM_UUID,
    )
    service.execute(preview.plan.id, task_id="task-media-resize")
    with database.session() as session:
        plan = session.get(VmMediaCreationPlan, preview.plan.id)
        assert plan is not None
        assert resize.digest == plan.resized_image_sha256
    database.dispose()


def test_recovered_resize_requires_capacity_and_persisted_hash(
    settings: Settings,
) -> None:
    database = Database(settings)
    upgrade_database(database)
    _seed(database)
    resize = Resize()
    resize.current = 2048
    remote = Remote()
    service = VmMediaCreationService(
        database,
        Authority(),  # type: ignore[arg-type]
        Copier(),  # type: ignore[arg-type]
        remote,  # type: ignore[arg-type]
        Storage(database),  # type: ignore[arg-type]
        Domains(database, remote),  # type: ignore[arg-type]
        ResourceLockStore(database),
        image_resize=resize,  # type: ignore[arg-type]
    )
    create = VmMediaCreateInput(
        **{
            **vars(_input()),
            "source_virtual_size_bytes": 1024,
            "target_capacity_bytes": 2048,
        }
    )
    preview = service.preview(create)
    with pytest.raises(RuntimeError, match="lacks verification metadata"):
        service._verify_recovered_resize(preview.plan, create)
    preview.plan.resized_image_sha256 = resize.digest
    service._verify_recovered_resize(preview.plan, create)
    database.dispose()


def _input() -> VmMediaCreateInput:
    return VmMediaCreateInput(
        media_item_id="media-1",
        media_sha256="a" * 64,
        media_format="qcow2",
        host_id="host-1",
        pool_resource_id="pool-1",
        pool_uuid=POOL_UUID,
        pool_generation=1,
        pool_hash="b" * 64,
        target_file_name="copied.qcow2",
        name="media-vm",
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
            MediaItem(
                id="media-1",
                relative_path="images/base.qcow2",
                file_name="base.qcow2",
                kind="qcow2",
                status=MediaStatus.AVAILABLE,
                size_bytes=1024,
                modified_ns=1,
                file_device=1,
                file_inode=1,
                sha256="a" * 64,
                image_format="qcow2",
                backing_chain_json="[]",
                observed_generation=1,
                first_seen_at=now,
                last_seen_at=now,
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
                persistent_hash="b" * 64,
                observed_generation=1,
                details_json=json.dumps(
                    {"pool_type": "dir", "active": True, "target_path": "/images"}
                ),
                labels_json="[]",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
