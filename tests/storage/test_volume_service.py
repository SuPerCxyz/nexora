from sqlalchemy import select

from nexora.db import Database
from nexora.resources.conflicts import ResourceWriteGuard
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.storage.contracts import StoragePoolCreateInput
from nexora.storage.service import StoragePoolService
from nexora.storage.volume_contracts import StorageVolumeCreateInput
from nexora.storage.volume_remote import StorageVolumeRemoteCommands
from nexora.storage.volume_service import StorageVolumeService
from nexora.tasks.locks import ResourceLockStore
from storage.support import PoolBackend


def test_create_qcow2_volume_requires_confirmation_and_verifies_identity(
    service: tuple[Database, StoragePoolService, PoolBackend],
) -> None:
    database, pools, backend = service
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
    with database.session() as session:
        pool = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                ResourceIndex.native_id == pool_preview.plan.pool_uuid,
            )
        )
        assert pool is not None and pool.persistent_hash is not None
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
    volumes = StorageVolumeService(
        database,
        pools.discovery,
        ResourceWriteGuard(database),
        ResourceLockStore(database),
        StorageVolumeRemoteCommands(database, pools.commands.executor),
    )

    preview = volumes.preview_create(create)
    volumes.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        pool_uuid=create.pool_uuid,
    )
    summary = volumes.execute_create(preview.plan.id, task_id="task-volume")

    assert "storage volume created" in summary
    assert "vm-disk.qcow2" in backend.volumes
    with database.session() as session:
        volume = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.resource_type == ResourceType.STORAGE_VOLUME,
                ResourceIndex.display_name == "vm-disk.qcow2",
            )
        )
        assert volume is not None
        assert create.pool_uuid == volume.parent_native_id
