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
from nexora.app import create_app
from nexora.config import Settings
from nexora.remote.commands import CommandSpec
from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.storage.contracts import StoragePoolCreateInput
from nexora.storage.task_contracts import (
    StoragePoolAction,
    StoragePoolLifecycleInput,
    StoragePoolTaskInput,
)
from nexora.tasks.definitions import TaskCreate

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="dedicated remote KVM integration environment is not configured",
)

DIR_NAME = "nexora-it-managed-dir"
DIR_TARGET = "/var/lib/libvirt/images/nexora-it-managed-dir"
NFS_NAME = "nexora-it-managed-netfs"
NFS_TARGET = "/var/lib/libvirt/nexora-it-managed-netfs"
NFS_EXPORT = "/srv/nexora-it-nfs"


def test_real_dir_and_netfs_pool_management(settings: Settings) -> None:
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        _cleanup_pool(client, host_id, DIR_NAME, DIR_TARGET)
        _cleanup_pool(client, host_id, NFS_NAME, NFS_TARGET)

        directory = _create_pool(
            client,
            StoragePoolCreateInput(
                host_id,
                DIR_NAME,
                "dir",
                DIR_TARGET,
            ),
        )
        _write_marker(client, host_id, f"{DIR_TARGET}/preserve-me.txt")
        _exercise_lifecycle(client, directory)
        _delete_pool(client, directory)
        _assert_remote(client, host_id, ("test", ("-f", f"{DIR_TARGET}/preserve-me.txt")))

        netfs = _create_pool(
            client,
            StoragePoolCreateInput(
                host_id,
                NFS_NAME,
                "netfs",
                NFS_TARGET,
                source_host="127.0.0.1",
                source_path=NFS_EXPORT,
                nfs_version="3",
                mount_options=("rw", "hard", "timeo=600"),
            ),
        )
        _exercise_lifecycle(client, netfs)
        _delete_pool(client, netfs)
        _assert_remote(client, host_id, ("test", ("-f", f"{NFS_EXPORT}/preserve-me.txt")))

        _remove_marker_and_target(client, host_id, DIR_TARGET)
        _remove_marker_and_target(client, host_id, NFS_TARGET)


def _create_pool(
    client: TestClient,
    create: StoragePoolCreateInput,
) -> ResourceIndex:
    service = client.app.state.storage_pool_service
    preview = service.preview_create(create)
    plan = service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id=create.host_id,
        pool_uuid=preview.plan.pool_uuid,
    )
    task_input = StoragePoolTaskInput(plan.id, plan.host_id, plan.pool_uuid, "create")
    task = client.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="storage.pool_change",
            title=f"Create {create.name}",
            idempotency_scope=f"integration:create:{plan.pool_uuid}",
            idempotency_key=plan.id,
            host_id=plan.host_id,
            resource_type=ResourceType.STORAGE_POOL,
            resource_id=plan.pool_uuid,
            total_steps=4,
            resumable=True,
            max_retries=2,
            recovery_strategy="retry_from_start",
            input_summary=task_input.encode(),
        )
    )
    _wait_task(client, task)
    return _pool(client, plan.host_id, plan.pool_uuid)


def _exercise_lifecycle(client: TestClient, pool: ResourceIndex) -> None:
    for action in (
        StoragePoolAction.STOP,
        StoragePoolAction.START,
        StoragePoolAction.AUTOSTART_DISABLE,
        StoragePoolAction.AUTOSTART_ENABLE,
        StoragePoolAction.REFRESH,
    ):
        current = _pool(client, pool.host_id, pool.native_id)
        task_input = StoragePoolLifecycleInput(action, _base(current))
        task = client.app.state.task_queue.enqueue(
            TaskCreate(
                task_type="storage.pool_lifecycle",
                title=f"{action} {pool.display_name}",
                idempotency_scope=f"integration:lifecycle:{pool.native_id}",
                idempotency_key=f"{action}:{current.observed_generation}",
                host_id=current.host_id,
                resource_type=ResourceType.STORAGE_POOL,
                resource_id=current.native_id,
                total_steps=3,
                input_summary=task_input.encode(),
            )
        )
        _wait_task(client, task)


def _delete_pool(client: TestClient, pool: ResourceIndex) -> None:
    current = _pool(client, pool.host_id, pool.native_id)
    service = client.app.state.storage_pool_delete_service
    preview = service.preview(_base(current))
    plan = service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id=current.host_id,
        pool_uuid=current.native_id,
    )
    task_input = StoragePoolTaskInput(plan.id, plan.host_id, plan.pool_uuid, "delete")
    task = client.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="storage.pool_change",
            title=f"Delete {pool.display_name}",
            idempotency_scope=f"integration:delete:{pool.native_id}",
            idempotency_key=plan.id,
            host_id=plan.host_id,
            resource_type=ResourceType.STORAGE_POOL,
            resource_id=plan.pool_uuid,
            total_steps=4,
            resumable=True,
            max_retries=2,
            recovery_strategy="retry_from_start",
            input_summary=task_input.encode(),
        )
    )
    _wait_task(client, task)


def _pool(client: TestClient, host_id: str, pool_uuid: str) -> ResourceIndex:
    with client.app.state.database.session() as session:
        resource = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                ResourceIndex.native_id == pool_uuid,
            )
        )
        assert resource is not None
        session.expunge(resource)
        return resource


def _base(pool: ResourceIndex) -> ResourceBaseVersion:
    return ResourceBaseVersion(
        pool.id,
        pool.host_id,
        ResourceType.STORAGE_POOL,
        pool.native_id,
        pool.observed_generation,
        pool.persistent_hash,
        None,
    )


def _cleanup_pool(
    client: TestClient,
    host_id: str,
    name: str,
    target: str,
) -> None:
    executor = client.app.state.remote_executor
    executor.run(
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "pool-destroy", name)),
        sudo=False,
        timeout=30,
    )
    executor.run(
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "pool-undefine", name)),
        sudo=False,
        timeout=30,
    )
    _remove_marker_and_target(client, host_id, target)


def _write_marker(client: TestClient, host_id: str, path: str) -> None:
    _assert_remote(client, host_id, ("touch", ("--", path)))


def _remove_marker_and_target(client: TestClient, host_id: str, target: str) -> None:
    executor = client.app.state.remote_executor
    executor.run(
        host_id,
        CommandSpec("rm", ("-f", "--", f"{target}/preserve-me.txt")),
        sudo=False,
        timeout=30,
    )
    executor.run(
        host_id,
        CommandSpec("rmdir", ("--", target)),
        sudo=False,
        timeout=30,
    )


def _assert_remote(
    client: TestClient,
    host_id: str,
    command: tuple[str, tuple[str, ...]],
) -> None:
    result = client.app.state.remote_executor.run(
        host_id,
        CommandSpec(*command),
        sudo=False,
        timeout=30,
    )
    assert 0 == result.exit_code, result.stderr.decode()
