import pytest
from lxml import etree
from sqlalchemy import select

from nexora.db import Database
from nexora.resources.conflicts import (
    ResourceBaseVersion,
    ResourceWriteConflict,
    ResourceWriteGuard,
)
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.storage.contracts import StoragePoolCreateInput
from nexora.storage.delete_service import StoragePoolDeleteService
from nexora.storage.lifecycle import StoragePoolLifecycleService
from nexora.storage.remote_ops import StoragePoolRemoteCommands
from nexora.storage.service import StoragePoolConflict, StoragePoolService
from nexora.storage.task_contracts import StoragePoolAction, StoragePoolLifecycleInput
from nexora.tasks.locks import ResourceLockStore
from storage.support import EmptyDomainDiscovery, PoolBackend


def test_create_pool_requires_confirmation_and_verifies_normalized_xml(
    service: tuple[Database, StoragePoolService, PoolBackend],
) -> None:
    _database, pools, backend = service
    create = _create()

    preview = pools.preview_create(create)
    pools.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        pool_uuid=preview.plan.pool_uuid,
    )
    summary = pools.execute_create(preview.plan.id, task_id="task-1")

    assert "storage pool created" in summary
    assert backend.active
    assert backend.autostart
    assert preview.plan.pool_uuid.encode() in backend.xml


def test_preview_rejects_existing_name_or_target(
    service: tuple[Database, StoragePoolService, PoolBackend],
) -> None:
    _database, pools, _backend = service
    first = pools.preview_create(_create())
    pools.confirm(
        first.plan.id,
        first.confirmation_token,
        host_id="host-1",
        pool_uuid=first.plan.pool_uuid,
    )
    pools.execute_create(first.plan.id, task_id="task-1")

    with pytest.raises(StoragePoolConflict):
        pools.preview_create(_create())


def test_retry_accepts_task_owned_matching_definition(
    service: tuple[Database, StoragePoolService, PoolBackend],
) -> None:
    _database, pools, backend = service
    preview = pools.preview_create(_create())
    pools.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        pool_uuid=preview.plan.pool_uuid,
    )
    backend.xml = preview.plan.proposed_xml

    summary = pools.execute_create(preview.plan.id, task_id="task-recovery")

    assert "already matches plan" in summary
    assert backend.active


def test_lifecycle_stops_pool_without_removing_definition(
    service: tuple[Database, StoragePoolService, PoolBackend],
) -> None:
    database, pools, backend = service
    preview = pools.preview_create(_create())
    pools.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        pool_uuid=preview.plan.pool_uuid,
    )
    pools.execute_create(preview.plan.id, task_id="task-create")
    with database.session() as session:
        resource = session.scalar(
            select(ResourceIndex).where(ResourceIndex.native_id == preview.plan.pool_uuid)
        )
        assert resource is not None
        base = ResourceBaseVersion(
            resource.id,
            resource.host_id,
            ResourceType.STORAGE_POOL,
            resource.native_id,
            resource.observed_generation,
            resource.persistent_hash,
            None,
        )
    lifecycle = StoragePoolLifecycleService(
        pools.discovery,
        pools.discovery.store,
        ResourceWriteGuard(database),
        ResourceLockStore(database),
        StoragePoolRemoteCommands(database, pools.commands.executor),
    )

    lifecycle.execute(
        StoragePoolLifecycleInput(StoragePoolAction.STOP, base),
        task_id="task-stop",
    )

    assert not backend.active
    assert backend.xml is not None


def test_delete_plan_undefines_pool_but_preserves_target_scope(
    service: tuple[Database, StoragePoolService, PoolBackend],
) -> None:
    database, pools, backend = service
    preview = pools.preview_create(_create())
    pools.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        pool_uuid=preview.plan.pool_uuid,
    )
    pools.execute_create(preview.plan.id, task_id="task-create")
    with database.session() as session:
        resource = session.scalar(
            select(ResourceIndex).where(ResourceIndex.native_id == preview.plan.pool_uuid)
        )
        assert resource is not None
        base = ResourceBaseVersion(
            resource.id,
            resource.host_id,
            ResourceType.STORAGE_POOL,
            resource.native_id,
            resource.observed_generation,
            resource.persistent_hash,
            None,
        )
    deletion = StoragePoolDeleteService(
        database,
        pools.discovery,
        EmptyDomainDiscovery(),  # type: ignore[arg-type]
        pools.discovery.store,
        ResourceWriteGuard(database),
        ResourceLockStore(database),
        StoragePoolRemoteCommands(database, pools.commands.executor),
    )

    delete_preview = deletion.preview(base)
    deletion.confirm(
        delete_preview.plan.id,
        delete_preview.confirmation_token,
        host_id="host-1",
        pool_uuid=preview.plan.pool_uuid,
    )
    summary = deletion.execute(delete_preview.plan.id, task_id="task-delete")

    assert "data_preserved=true" in summary
    assert backend.xml is None
    assert backend.target_exists


def test_delete_blocks_out_of_band_xml_change_after_preview(
    service: tuple[Database, StoragePoolService, PoolBackend],
) -> None:
    database, pools, backend = service
    create_preview = pools.preview_create(_create())
    pools.confirm(
        create_preview.plan.id,
        create_preview.confirmation_token,
        host_id="host-1",
        pool_uuid=create_preview.plan.pool_uuid,
    )
    pools.execute_create(create_preview.plan.id, task_id="task-create")
    with database.session() as session:
        resource = session.scalar(
            select(ResourceIndex).where(ResourceIndex.native_id == create_preview.plan.pool_uuid)
        )
        assert resource is not None
        base = ResourceBaseVersion(
            resource.id,
            resource.host_id,
            ResourceType.STORAGE_POOL,
            resource.native_id,
            resource.observed_generation,
            resource.persistent_hash,
            None,
        )
    deletion = StoragePoolDeleteService(
        database,
        pools.discovery,
        EmptyDomainDiscovery(),  # type: ignore[arg-type]
        pools.discovery.store,
        ResourceWriteGuard(database),
        ResourceLockStore(database),
        StoragePoolRemoteCommands(database, pools.commands.executor),
    )
    delete_preview = deletion.preview(base)
    deletion.confirm(
        delete_preview.plan.id,
        delete_preview.confirmation_token,
        host_id="host-1",
        pool_uuid=create_preview.plan.pool_uuid,
    )
    assert backend.xml is not None
    root = etree.fromstring(backend.xml)
    root.find("target/path").text = "/var/lib/libvirt/out-of-band"
    backend.xml = etree.tostring(root)

    with pytest.raises(ResourceWriteConflict):
        deletion.execute(delete_preview.plan.id, task_id="task-delete")

    assert backend.xml is not None


def _create() -> StoragePoolCreateInput:
    return StoragePoolCreateInput(
        host_id="host-1",
        name="images",
        pool_type="dir",
        target_path="/var/lib/libvirt/nexora-images",
    )
