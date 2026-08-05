import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from integration.test_remote_kvm import (
    _initialize,
    _onboard,
    _resource,
    _wait_for_task_types,
)
from integration.test_remote_vm_create import _require_remote
from nexora.app import create_app
from nexora.config import Settings
from nexora.media.inspection import ImageInfo
from nexora.media.models import MediaItem
from nexora.media.scanner import MediaScanner
from nexora.remote.commands import CommandSpec
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.models import Task, TaskStatus
from nexora.vms.cloud_init import build_cloud_init_documents
from nexora.vms.cloud_password import hash_guest_password
from nexora.vms.media_creation_contracts import VmMediaCreateInput
from nexora.vms.media_creation_models import VmMediaCreationPlan
from nexora.vms.media_creation_tasks import VmMediaCreationTaskInput

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="remote KVM platform-image VM integration environment is not configured",
)
VM_NAME = "nexora-it-media-create"
VM_UUID = "66ee0134-a825-4a64-9c33-b8c13a9861f6"
TARGET_NAME = "nexora-it-media-create.raw"
SEED_NAME = f"nexora-cloudinit-{VM_UUID}.iso"
SSH_PUBLIC_KEY = "ssh-ed25519 " + "A" * 68 + " integration@test"


class RawInspector:
    def inspect(self, path: Path) -> ImageInfo:
        return ImageInfo("raw", path.stat().st_size, ())


@pytest.mark.parametrize("include_ipv4", [False, True], ids=["ipv6-only", "dual-stack"])
def test_copy_platform_image_then_create_vm_through_resumable_task(
    settings: Settings,
    include_ipv4: bool,
) -> None:
    source = settings.library_dir / "images" / "integration.raw"
    source.parent.mkdir(parents=True)
    with source.open("wb") as stream:
        stream.truncate(8 * 1024 * 1024)
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        pool = _resource(client, host_id, ResourceType.STORAGE_POOL, "nexora-it-dir")
        network = _resource(client, host_id, ResourceType.LIBVIRT_NETWORK, "default")
        _cleanup(client, host_id, pool.native_id)
        try:
            MediaScanner(
                settings.library_dir,
                client.app.state.media_index_store,
                RawInspector(),
            ).scan()
            media = next(
                item
                for item in client.app.state.media_index_store.list_items()
                if item.file_name == source.name
            )
            create = _input(host_id, pool, network, media, include_ipv4=include_ipv4)
            preview = client.app.state.vm_media_creation_service.preview(create)
            plan = client.app.state.vm_media_creation_service.confirm(
                preview.plan.id,
                preview.confirmation_token,
                host_id=host_id,
                vm_uuid=VM_UUID,
            )
            task = client.app.state.task_queue.enqueue(
                TaskCreate(
                    task_type="vm.create_from_media",
                    title="Create VM from integration platform image",
                    idempotency_scope=f"integration:vm-media-create:{VM_UUID}",
                    idempotency_key=plan.id,
                    host_id=host_id,
                    vm_uuid=VM_UUID,
                    resource_type=ResourceType.VIRTUAL_MACHINE,
                    resource_id=VM_UUID,
                    total_steps=5,
                    resumable=True,
                    recovery_strategy="resume_from_checkpoint",
                    input_summary=VmMediaCreationTaskInput(
                        plan.id,
                        host_id,
                        VM_UUID,
                    ).encode(),
                )
            )
            _wait_media_task(client, task.id, plan.id)
            _verify_seed_recovery(client, host_id, create, task.id)
            _verify_and_start(client, host_id, network)
        finally:
            _cleanup(client, host_id, pool.native_id)


def _input(
    host_id: str,
    pool: ResourceIndex,
    network: ResourceIndex,
    media: MediaItem,
    *,
    include_ipv4: bool,
) -> VmMediaCreateInput:
    assert pool.persistent_hash is not None
    assert network.persistent_hash is not None
    return VmMediaCreateInput(
        media_item_id=media.id,
        media_sha256=media.sha256,
        media_format="raw",
        host_id=host_id,
        pool_resource_id=pool.id,
        pool_uuid=pool.native_id,
        pool_generation=pool.observed_generation,
        pool_hash=pool.persistent_hash,
        target_file_name=TARGET_NAME,
        name=VM_NAME,
        memory_mib=512,
        vcpus=1,
        vm_uuid=VM_UUID,
        network_kind="network",
        network_resource_id=network.id,
        network_native_id=network.native_id,
        network_generation=network.observed_generation,
        network_hash=network.persistent_hash,
        network_name=network.display_name,
        network_mac="52:54:00:12:34:56",
        cloud_hostname="nexora-it-cloud.test",
        cloud_username="nexora",
        cloud_ssh_public_key=SSH_PUBLIC_KEY,
        cloud_password_hash=hash_guest_password(
            "Nexora-integration-only-2026!",
            "Nexora-integration-only-2026!",
        ),
        cloud_network_mode="static",
        cloud_ipv4_cidr="192.168.122.249/24" if include_ipv4 else None,
        cloud_ipv4_gateway="192.168.122.1" if include_ipv4 else None,
        cloud_ipv6_cidr="2001:db8:122::249/64",
        cloud_ipv6_gateway="2001:db8:122::1",
        cloud_dns_addresses=("2001:4860:4860::8888", "1.1.1.1")
        if include_ipv4
        else ("2001:4860:4860::8888",),
        source_virtual_size_bytes=media.virtual_size_bytes,
        target_capacity_bytes=16 * 1024 * 1024,
    )


def _verify_and_start(
    client: TestClient,
    host_id: str,
    original_network: ResourceIndex,
) -> None:
    vm = _resource(client, host_id, ResourceType.VIRTUAL_MACHINE, VM_NAME)
    assert VM_UUID == vm.native_id
    details = json.loads(vm.details_json)
    assert "shut off" == str(details["state"]).lower()
    assert any(
        disk["device"] == "disk"
        and disk["source"].endswith(TARGET_NAME)
        and disk["format"] == "raw"
        for disk in details["disks"]
    )
    disk_path = next(disk["source"] for disk in details["disks"] if disk["device"] == "disk")
    resize = client.app.state.vm_media_creation_service.image_resize
    assert resize is not None
    assert 16 * 1024 * 1024 == resize.virtual_size(host_id, disk_path)
    assert any(
        disk["device"] == "cdrom"
        and disk["source"].endswith(SEED_NAME)
        and disk["target"] == "sdb"
        and disk["readonly"]
        for disk in details["disks"]
    )
    current_network = _resource(client, host_id, ResourceType.LIBVIRT_NETWORK, "default")
    assert original_network.persistent_hash == current_network.persistent_hash
    _require_remote(
        client,
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "start", VM_UUID)),
    )
    state = _require_remote(
        client,
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "domstate", VM_UUID)),
    )
    assert b"running" in state.lower()


def _cleanup(client: TestClient, host_id: str, pool_uuid: str) -> None:
    executor = client.app.state.remote_executor
    for action in ("destroy", "undefine"):
        executor.run(
            host_id,
            CommandSpec("virsh", ("-c", "qemu:///system", action, VM_UUID)),
            sudo=False,
            timeout=30,
        )
    for name in (TARGET_NAME, SEED_NAME):
        executor.run(
            host_id,
            CommandSpec(
                "virsh",
                ("-c", "qemu:///system", "vol-delete", name, "--pool", pool_uuid),
            ),
            sudo=False,
            timeout=30,
        )
    domain = executor.run(
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "dominfo", VM_UUID)),
        sudo=False,
        timeout=30,
    )
    assert domain.exit_code != 0
    for name in (TARGET_NAME, SEED_NAME):
        volume = executor.run(
            host_id,
            CommandSpec(
                "virsh",
                ("-c", "qemu:///system", "vol-info", name, "--pool", pool_uuid),
            ),
            sudo=False,
            timeout=30,
        )
        assert volume.exit_code != 0


def _verify_seed_recovery(
    client: TestClient,
    host_id: str,
    create: VmMediaCreateInput,
    task_id: str,
) -> None:
    vm = _resource(client, host_id, ResourceType.VIRTUAL_MACHINE, VM_NAME)
    details = json.loads(vm.details_json)
    seed_path = next(
        disk["source"]
        for disk in details["disks"]
        if disk["device"] == "cdrom" and disk["target"] == "sdb"
    )
    documents = build_cloud_init_documents(create)
    assert documents is not None
    assert b'"2001:db8:122::249/64"' in documents.network_config
    assert b'"to":"::/0"' in documents.network_config
    assert b'"via":"2001:db8:122::1"' in documents.network_config
    if create.cloud_ipv4_cidr is None:
        assert b'"to":"0.0.0.0/0"' not in documents.network_config
    else:
        assert b'"192.168.122.249/24"' in documents.network_config
    remote = client.app.state.vm_media_creation_service.cloud_init
    assert remote is not None
    assert seed_path == remote.publish(
        host_id,
        seed_path,
        documents,
        task_id=task_id,
    )


def _wait_media_task(client: TestClient, task_id: str, plan_id: str) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        with client.app.state.database.session() as session:
            task = session.get(Task, task_id)
            plan = session.get(VmMediaCreationPlan, plan_id)
            assert task is not None
            assert plan is not None
            current = task.status
            error = plan.error_message
        if current == TaskStatus.SUCCEEDED:
            return
        assert current not in {
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }, error
        time.sleep(0.1)
    raise AssertionError("platform-image VM task did not finish")
