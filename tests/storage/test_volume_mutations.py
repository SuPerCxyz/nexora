import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from nexora.db import Database
from nexora.resources.conflicts import ResourceWriteGuard
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.storage.contracts import StoragePoolCreateInput
from nexora.storage.service import StoragePoolService
from nexora.storage.volume_contracts import (
    StorageVolumeCreateInput,
    StorageVolumeMutationInput,
)
from nexora.storage.volume_mutations import StorageVolumeMutationService
from nexora.storage.volume_remote import StorageVolumeRemoteCommands
from nexora.storage.volume_service import StorageVolumeConflict, StorageVolumeService
from nexora.tasks.locks import ResourceLockStore
from storage.support import EmptyDomainDiscovery, PoolBackend


def test_resize_then_delete_unreferenced_volume(
    service: tuple[Database, StoragePoolService, PoolBackend],
) -> None:
    database, pools, backend = service
    mutations, pool, volume = _create_volume(database, pools)
    resize = _mutation(pool, volume, target=20 * 1024**3)

    preview = mutations.preview_resize(resize)
    assert "10737418240" in preview.plan.diff_text
    assert "21474836480" in preview.plan.diff_text
    mutations.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        pool_uuid=pool.native_id,
    )
    summary = mutations.execute(preview.plan.id, task_id="task-resize")

    assert "storage volume resized" in summary
    refreshed_pool, refreshed_volume = _resources(database)
    details = json.loads(refreshed_volume.details_json)
    assert details["capacity_bytes"] == 20 * 1024**3

    delete = _mutation(refreshed_pool, refreshed_volume, target=None)
    preview = mutations.preview_delete(delete)
    assert "+++ /dev/null" in preview.plan.diff_text
    mutations.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        pool_uuid=refreshed_pool.native_id,
    )
    summary = mutations.execute(preview.plan.id, task_id="task-delete")

    assert "storage volume deleted" in summary
    assert "vm-disk.qcow2" not in backend.volumes
    _, deleted = _resources(database)
    assert deleted.status == ResourceStatus.MISSING


def test_active_vm_reference_blocks_resize_and_delete(
    service: tuple[Database, StoragePoolService, PoolBackend],
) -> None:
    database, pools, _backend = service
    mutations, pool, volume = _create_volume(database, pools)
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(
            ResourceIndex(
                id="vm-active",
                host_id="host-1",
                resource_type=ResourceType.VIRTUAL_MACHINE,
                native_id="11111111-1111-1111-1111-111111111111",
                display_name="important-vm",
                status=ResourceStatus.MANAGED,
                source="existing",
                observed_generation=1,
                details_json=json.dumps(
                    {
                        "state": "running",
                        "disks": [
                            {
                                "source": "vm-disk.qcow2",
                                "pool": "images",
                            }
                        ],
                    }
                ),
                labels_json="[]",
                first_seen_at=now,
                last_seen_at=now,
            )
        )

    with pytest.raises(StorageVolumeConflict, match="active VM important-vm"):
        mutations.preview_resize(_mutation(pool, volume, target=20 * 1024**3))
    with pytest.raises(StorageVolumeConflict, match="referenced by VM important-vm"):
        mutations.preview_delete(_mutation(pool, volume, target=None))


def _create_volume(
    database: Database,
    pools: StoragePoolService,
) -> tuple[StorageVolumeMutationService, ResourceIndex, ResourceIndex]:
    pool_preview = pools.preview_create(
        StoragePoolCreateInput(
            host_id="host-1",
            name="images",
            pool_type="dir",
            target_path="/var/lib/libvirt/nexora-images",
        )
    )
    pools.confirm(
        pool_preview.plan.id,
        pool_preview.confirmation_token,
        host_id="host-1",
        pool_uuid=pool_preview.plan.pool_uuid,
    )
    pools.execute_create(pool_preview.plan.id, task_id="task-pool")
    pool, _ = _resources(database, volume_required=False)
    assert pool.persistent_hash is not None
    commands = StorageVolumeRemoteCommands(database, pools.commands.executor)
    volumes = StorageVolumeService(
        database,
        pools.discovery,
        ResourceWriteGuard(database),
        ResourceLockStore(database),
        commands,
    )
    create = StorageVolumeCreateInput(
        "host-1",
        pool.id,
        pool.native_id,
        pool.observed_generation,
        pool.persistent_hash,
        "vm-disk.qcow2",
        "qcow2",
        10 * 1024**3,
    )
    preview = volumes.preview_create(create)
    volumes.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        pool_uuid=pool.native_id,
    )
    volumes.execute_create(preview.plan.id, task_id="task-create")
    pool, volume = _resources(database)
    mutations = StorageVolumeMutationService(
        database,
        pools.discovery,
        EmptyDomainDiscovery(),  # type: ignore[arg-type]
        ResourceWriteGuard(database),
        ResourceLockStore(database),
        commands,
    )
    return mutations, pool, volume


def _mutation(
    pool: ResourceIndex,
    volume: ResourceIndex,
    *,
    target: int | None,
) -> StorageVolumeMutationInput:
    assert pool.persistent_hash is not None
    assert volume.persistent_hash is not None
    details = json.loads(volume.details_json)
    return StorageVolumeMutationInput(
        host_id=volume.host_id,
        pool_resource_id=pool.id,
        pool_uuid=pool.native_id,
        pool_generation=pool.observed_generation,
        pool_hash=pool.persistent_hash,
        volume_resource_id=volume.id,
        volume_native_id=volume.native_id,
        volume_generation=volume.observed_generation,
        volume_hash=volume.persistent_hash,
        volume_key=str(details["key"]),
        volume_name=volume.display_name,
        current_capacity_bytes=int(details["capacity_bytes"]),
        target_capacity_bytes=target,
    )


def _resources(
    database: Database,
    *,
    volume_required: bool = True,
) -> tuple[ResourceIndex, ResourceIndex]:
    with database.session() as session:
        pool = session.scalar(
            select(ResourceIndex).where(ResourceIndex.resource_type == ResourceType.STORAGE_POOL)
        )
        volume = session.scalar(
            select(ResourceIndex).where(ResourceIndex.resource_type == ResourceType.STORAGE_VOLUME)
        )
        assert pool is not None
        if volume_required:
            assert volume is not None
        return pool, volume  # type: ignore[return-value]
