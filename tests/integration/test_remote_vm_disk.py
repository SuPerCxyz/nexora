import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from integration.test_remote_kvm import (
    _initialize,
    _onboard,
    _wait_for_task_types,
    _wait_task,
)
from integration.test_remote_storage import (
    DIR_NAME,
    DIR_TARGET,
    _cleanup_pool,
    _create_pool,
    _delete_pool,
    _remove_marker_and_target,
)
from nexora.app import create_app
from nexora.config import Settings
from nexora.remote.commands import CommandSpec
from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.storage.contracts import StoragePoolCreateInput
from nexora.storage.volume_contracts import StorageVolumeCreateInput
from nexora.storage.volume_tasks import StorageVolumeTaskInput
from nexora.tasks.definitions import TaskCreate
from nexora.vms.contracts import VmChangeTaskInput
from nexora.xml import DiskDetachChange

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="dedicated remote KVM integration environment is not configured",
)
VM_NAME = "nexora-it-existing"
VOLUME_NAME = "nexora-it-vm-disk.qcow2"


def test_real_persistent_vm_disk_attach_detach_preserves_volume(
    settings: Settings,
) -> None:
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        vm = _vm(client, host_id)
        _cleanup_vm_volume(client, host_id)
        _cleanup_pool(client, host_id, DIR_NAME, DIR_TARGET)
        pool = _create_pool(
            client,
            StoragePoolCreateInput(host_id, DIR_NAME, "dir", DIR_TARGET),
        )
        volume = _create_volume(client, host_id, pool)

        service = client.app.state.vm_disk_change_service
        preview = service.preview_attach(
            _base(vm),
            _base(volume),
            bus="virtio",
        )
        plan = service.confirm(
            preview.plan.id,
            preview.confirmation_token,
            host_id=host_id,
            vm_uuid=vm.native_id,
            change_type="disk_attach",
        )
        _execute_disk_plan(client, vm, plan.id, "disk_attach")
        vm = _vm(client, host_id)
        disk = next(item for item in _details(vm)["disks"] if item["source"] == _path(volume))

        preview = service.preview_detach(
            _base(vm),
            DiskDetachChange(
                str(disk["target"]),
                str(disk["bus"]),
                str(disk["device"]),
                str(disk["source"]),
            ),
        )
        plan = service.confirm(
            preview.plan.id,
            preview.confirmation_token,
            host_id=host_id,
            vm_uuid=vm.native_id,
            change_type="disk_detach",
        )
        _execute_disk_plan(client, vm, plan.id, "disk_detach")
        assert all(
            item["source"] != _path(volume) for item in _details(_vm(client, host_id))["disks"]
        )
        _assert_volume_exists(client, host_id, pool.native_id)

        _cleanup_vm_volume(client, host_id)
        _delete_pool(client, pool)
        _remove_marker_and_target(client, host_id, DIR_TARGET)


def _create_volume(
    client: TestClient,
    host_id: str,
    pool: ResourceIndex,
) -> ResourceIndex:
    assert pool.persistent_hash is not None
    service = client.app.state.storage_volume_service
    preview = service.preview_create(
        StorageVolumeCreateInput(
            host_id,
            pool.id,
            pool.native_id,
            pool.observed_generation,
            pool.persistent_hash,
            VOLUME_NAME,
            "qcow2",
            8 * 1024**2,
        )
    )
    plan = service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id=host_id,
        pool_uuid=pool.native_id,
    )
    task_input = StorageVolumeTaskInput(plan.id, host_id, pool.native_id, "create")
    task = client.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="storage.volume_change",
            title="Create VM disk integration volume",
            idempotency_scope=f"integration:vm-disk:{pool.native_id}",
            idempotency_key=plan.id,
            host_id=host_id,
            resource_type=ResourceType.STORAGE_VOLUME,
            resource_id=pool.native_id,
            total_steps=3,
            resumable=True,
            recovery_strategy="retry_from_start",
            input_summary=task_input.encode(),
        )
    )
    _wait_task(client, task)
    with client.app.state.database.session() as session:
        volume = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == ResourceType.STORAGE_VOLUME,
                ResourceIndex.display_name == VOLUME_NAME,
                ResourceIndex.status == ResourceStatus.MANAGED,
            )
        )
        assert volume is not None
        return volume


def _cleanup_vm_volume(client: TestClient, host_id: str) -> None:
    executor = client.app.state.remote_executor
    executor.run(
        host_id,
        CommandSpec(
            "virsh",
            (
                "-c",
                "qemu:///system",
                "detach-disk",
                VM_NAME,
                f"{DIR_TARGET}/{VOLUME_NAME}",
                "--config",
            ),
        ),
        sudo=False,
        timeout=30,
    )
    executor.run(
        host_id,
        CommandSpec(
            "virsh",
            ("-c", "qemu:///system", "vol-delete", VOLUME_NAME, "--pool", DIR_NAME),
        ),
        sudo=False,
        timeout=30,
    )


def _execute_disk_plan(
    client: TestClient,
    vm: ResourceIndex,
    plan_id: str,
    change_type: str,
) -> None:
    task_input = VmChangeTaskInput(plan_id, vm.host_id, vm.native_id, change_type)
    task = client.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.disk_change",
            title=f"{change_type} integration disk",
            idempotency_scope=f"integration:vm:{vm.native_id}:disk",
            idempotency_key=plan_id,
            host_id=vm.host_id,
            vm_uuid=vm.native_id,
            resource_type=ResourceType.VIRTUAL_MACHINE,
            resource_id=vm.id,
            total_steps=3,
            resumable=False,
            recovery_strategy="verify_only",
            input_summary=task_input.encode(),
        )
    )
    _wait_task(client, task)


def _vm(client: TestClient, host_id: str) -> ResourceIndex:
    with client.app.state.database.session() as session:
        vm = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                ResourceIndex.display_name == VM_NAME,
                ResourceIndex.status == ResourceStatus.MANAGED,
            )
        )
        assert vm is not None
        return vm


def _base(resource: ResourceIndex) -> ResourceBaseVersion:
    return ResourceBaseVersion(
        resource.id,
        resource.host_id,
        resource.resource_type,
        resource.native_id,
        resource.observed_generation,
        resource.persistent_hash,
        resource.live_hash,
    )


def _details(resource: ResourceIndex) -> dict[str, object]:
    import json

    return json.loads(resource.details_json)


def _path(volume: ResourceIndex) -> str:
    value = _details(volume).get("path")
    assert isinstance(value, str)
    return value


def _assert_volume_exists(
    client: TestClient,
    host_id: str,
    pool_uuid: str,
) -> None:
    result = client.app.state.remote_executor.run(
        host_id,
        CommandSpec(
            "virsh",
            ("-c", "qemu:///system", "vol-info", VOLUME_NAME, "--pool", pool_uuid),
        ),
        sudo=False,
        timeout=30,
    )
    assert 0 == result.exit_code
