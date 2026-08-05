import json
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
    NFS_EXPORT,
    NFS_NAME,
    NFS_TARGET,
    _cleanup_pool,
    _create_pool,
    _delete_pool,
    _remove_marker_and_target,
)
from nexora.app import create_app
from nexora.config import Settings
from nexora.remote.commands import CommandSpec
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.storage.contracts import StoragePoolCreateInput
from nexora.storage.volume_contracts import (
    StorageVolumeCreateInput,
    StorageVolumeMutationInput,
)
from nexora.storage.volume_tasks import StorageVolumeTaskInput
from nexora.tasks.definitions import TaskCreate

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="dedicated remote KVM integration environment is not configured",
)
VOLUME_NAME = "nexora-it-volume.qcow2"


@pytest.mark.parametrize(
    ("pool_name", "target_path", "pool_type"),
    [
        pytest.param(DIR_NAME, DIR_TARGET, "dir", id="dir"),
        pytest.param(NFS_NAME, NFS_TARGET, "netfs", id="netfs"),
    ],
)
def test_real_qcow2_volume_create_resize_and_delete(
    settings: Settings,
    pool_name: str,
    target_path: str,
    pool_type: str,
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
        _cleanup_volume(client, host_id, pool_name)
        _cleanup_pool(client, host_id, pool_name, target_path)
        create_pool = StoragePoolCreateInput(host_id, pool_name, pool_type, target_path)
        if pool_type == "netfs":
            create_pool = StoragePoolCreateInput(
                host_id,
                pool_name,
                pool_type,
                target_path,
                source_host="127.0.0.1",
                source_path=NFS_EXPORT,
                nfs_version="3",
                mount_options=("rw", "hard", "timeo=600"),
            )
        pool = _create_pool(
            client,
            create_pool,
        )
        assert pool.persistent_hash is not None
        create = StorageVolumeCreateInput(
            host_id,
            pool.id,
            pool.native_id,
            pool.observed_generation,
            pool.persistent_hash,
            VOLUME_NAME,
            "qcow2",
            8 * 1024**2,
        )
        service = client.app.state.storage_volume_service
        preview = service.preview_create(create)
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
                title="Create integration volume",
                idempotency_scope=f"integration:volume:{pool.native_id}",
                idempotency_key=plan.id,
                host_id=host_id,
                resource_type="storage_volume",
                resource_id=pool.native_id,
                total_steps=3,
                resumable=True,
                max_retries=2,
                recovery_strategy="retry_from_start",
                input_summary=task_input.encode(),
            )
        )
        _wait_task(client, task)
        result = client.app.state.remote_executor.run(
            host_id,
            CommandSpec(
                "virsh",
                (
                    "-c",
                    "qemu:///system",
                    "vol-info",
                    VOLUME_NAME,
                    "--pool",
                    pool.native_id,
                ),
            ),
            sudo=False,
            timeout=30,
        )
        assert 0 == result.exit_code

        volume = _volume(client, host_id, pool.native_id)
        resize = _mutation(pool, volume, target=16 * 1024**2)
        _execute_mutation(client, resize, "resize")
        volume = _volume(client, host_id, pool.native_id)
        assert 16 * 1024**2 == json.loads(volume.details_json)["capacity_bytes"]

        delete = _mutation(pool, volume, target=None)
        _execute_mutation(client, delete, "delete")
        with client.app.state.database.session() as session:
            deleted = session.get(ResourceIndex, volume.id)
            assert deleted is not None
            assert "missing" == deleted.status

        _delete_pool(client, pool)
        _remove_marker_and_target(client, host_id, target_path)


def _volume(client: TestClient, host_id: str, pool_uuid: str) -> ResourceIndex:
    with client.app.state.database.session() as session:
        volume = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == ResourceType.STORAGE_VOLUME,
                ResourceIndex.parent_native_id == pool_uuid,
                ResourceIndex.display_name == VOLUME_NAME,
            )
        )
        assert volume is not None
        return volume


def _mutation(
    pool: ResourceIndex,
    volume: ResourceIndex,
    *,
    target: int | None,
) -> StorageVolumeMutationInput:
    details = json.loads(volume.details_json)
    assert pool.persistent_hash is not None
    assert volume.persistent_hash is not None
    return StorageVolumeMutationInput(
        volume.host_id,
        pool.id,
        pool.native_id,
        pool.observed_generation,
        pool.persistent_hash,
        volume.id,
        volume.native_id,
        volume.observed_generation,
        volume.persistent_hash,
        str(details["key"]),
        volume.display_name,
        int(details["capacity_bytes"]),
        target,
    )


def _execute_mutation(
    client: TestClient,
    change: StorageVolumeMutationInput,
    operation: str,
) -> None:
    service = client.app.state.storage_volume_mutation_service
    preview = (
        service.preview_resize(change) if operation == "resize" else service.preview_delete(change)
    )
    plan = service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id=change.host_id,
        pool_uuid=change.pool_uuid,
    )
    task_input = StorageVolumeTaskInput(
        plan.id,
        change.host_id,
        change.pool_uuid,
        operation,
        change.volume_native_id,
    )
    task = client.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="storage.volume_change",
            title=f"{operation} integration volume",
            idempotency_scope=f"integration:volume:{change.volume_native_id}",
            idempotency_key=plan.id,
            host_id=change.host_id,
            resource_type="storage_volume",
            resource_id=change.volume_native_id,
            total_steps=3,
            resumable=False,
            recovery_strategy="verify_only",
            input_summary=task_input.encode(),
        )
    )
    _wait_task(client, task)


def _cleanup_volume(client: TestClient, host_id: str, pool_name: str) -> None:
    client.app.state.remote_executor.run(
        host_id,
        CommandSpec(
            "virsh",
            ("-c", "qemu:///system", "vol-delete", VOLUME_NAME, "--pool", pool_name),
        ),
        sudo=False,
        timeout=30,
    )
