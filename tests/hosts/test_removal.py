from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import (
    AuthenticationMethod,
    Host,
    HostFingerprint,
    HostStatus,
    SudoMode,
)
from nexora.hosts.removal import HostRemovalConflict, HostRemovalService
from nexora.hosts.removal_inventory import RemoteCleanupInventory
from nexora.hosts.removal_models import (
    HostRemovalMode,
    HostRemovalPlan,
    HostRemovalPlanStatus,
    HostRemovalTombstone,
)
from nexora.remote.host_key_store import HostKeyStore
from nexora.remote.host_keys import HostKeyCandidate
from nexora.resources.contracts import ResourceObservation
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.queue import TaskQueue


class NoRemoteCleanup:
    def discover(self, _host_id: str, *, sudo: bool) -> RemoteCleanupInventory:
        raise AssertionError(f"local-only removal used remote cleanup: sudo={sudo}")

    def cleanup(
        self,
        _host_id: str,
        _inventory: RemoteCleanupInventory,
        *,
        sudo: bool,
    ) -> None:
        raise AssertionError(f"local-only removal used remote cleanup: sudo={sudo}")


class StatefulCleanup:
    def __init__(self) -> None:
        self.inventory = RemoteCleanupInventory(
            ("/tmp/nexora-operation-1",),
            ("nexora-rollback.service",),
        )
        self.cleaned = False

    def discover(self, _host_id: str, *, sudo: bool) -> RemoteCleanupInventory:
        del sudo
        return RemoteCleanupInventory((), ()) if self.cleaned else self.inventory

    def cleanup(
        self,
        _host_id: str,
        inventory: RemoteCleanupInventory,
        *,
        sudo: bool,
    ) -> None:
        del sudo
        assert self.inventory == inventory
        self.cleaned = True


def test_local_only_removal_cascades_management_data_and_keeps_tombstone(
    settings: Settings,
) -> None:
    database, service, host_keys = _runtime(settings)
    preview = service.preview("host-1", HostRemovalMode.LOCAL_ONLY)
    plan = service.confirm(preview.plan.id, preview.confirmation_token, "node")
    task = TaskQueue(database).enqueue(
        TaskCreate(
            task_type="host.remove",
            title="remove",
            idempotency_scope="remove",
            idempotency_key="one",
            host_id="host-1",
            resource_id=plan.id,
        )
    )

    summary = service.execute(plan.id, task_id=task.id)

    assert "business_resources_removed=0" in summary
    assert not host_keys.path_for("host-1").exists()
    with database.session() as session:
        assert session.get(Host, "host-1") is None
        assert 0 == session.scalar(select(func.count()).select_from(ResourceIndex))
        stored_plan = session.get(HostRemovalPlan, plan.id)
        tombstone = session.scalar(select(HostRemovalTombstone))
        assert stored_plan is not None
        assert HostRemovalPlanStatus.SUCCEEDED == stored_plan.status
        assert tombstone is not None
        assert "node.example.test" == tombstone.address
        assert '"business_resources_removed":0' in tombstone.cleanup_summary_json
    database.dispose()


def test_confirmed_temporary_cleanup_is_verified_before_local_removal(
    settings: Settings,
) -> None:
    cleanup = StatefulCleanup()
    database, service, _host_keys = _runtime(settings, cleanup)
    preview = service.preview("host-1", HostRemovalMode.CLEAN_TEMPORARY)
    plan = service.confirm(preview.plan.id, preview.confirmation_token, "node")
    task = TaskQueue(database).enqueue(
        TaskCreate(
            task_type="host.remove",
            title="remove",
            idempotency_scope="remove",
            idempotency_key="clean",
            host_id="host-1",
            resource_id=plan.id,
        )
    )

    service.execute(plan.id, task_id=task.id)

    assert cleanup.cleaned
    with database.session() as session:
        tombstone = session.scalar(select(HostRemovalTombstone))
        assert tombstone is not None
        assert '"remote_paths_removed":1' in tombstone.cleanup_summary_json
        assert '"remote_units_removed":1' in tombstone.cleanup_summary_json
    database.dispose()


def test_changed_remote_inventory_blocks_removal_and_restores_host_status(
    settings: Settings,
) -> None:
    cleanup = StatefulCleanup()
    database, service, _host_keys = _runtime(settings, cleanup)
    preview = service.preview("host-1", HostRemovalMode.CLEAN_TEMPORARY)
    plan = service.confirm(preview.plan.id, preview.confirmation_token, "node")
    cleanup.inventory = RemoteCleanupInventory(("/tmp/nexora-different",), ())
    task = TaskQueue(database).enqueue(
        TaskCreate(
            task_type="host.remove",
            title="remove",
            idempotency_scope="remove",
            idempotency_key="changed",
            host_id="host-1",
            resource_id=plan.id,
        )
    )

    with pytest.raises(HostRemovalConflict, match="inventory changed"):
        service.execute(plan.id, task_id=task.id)

    with database.session() as session:
        host = session.get(Host, "host-1")
        stored_plan = session.get(HostRemovalPlan, plan.id)
        assert host is not None
        assert HostStatus.READY == host.status
        assert stored_plan is not None
        assert HostRemovalPlanStatus.FAILED == stored_plan.status
    database.dispose()


def _runtime(
    settings: Settings,
    cleanup=None,
) -> tuple[Database, HostRemovalService, HostKeyStore]:
    database = Database(settings)
    upgrade_database(database)
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
            HostFingerprint(
                host_id="host-1",
                key_type="ssh-ed25519",
                key_data="a2V5",
                fingerprint="SHA256:test",
                trust_state="trusted",
                discovered_at=now,
                trusted_at=now,
            )
        )
    ResourceIndexStore(database).apply_snapshot(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        [
            ResourceObservation(
                native_id="11111111-1111-1111-1111-111111111111",
                display_name="existing-vm",
                status=ResourceStatus.MANAGED,
                persistent_hash="hash",
                live_hash=None,
            )
        ],
    )
    host_keys = HostKeyStore(settings.data_dir / "hostkeys")
    host_keys.save(
        "host-1",
        [HostKeyCandidate("node.example.test", 22, "ssh-ed25519", "a2V5")],
    )
    return (
        database,
        HostRemovalService(database, cleanup or NoRemoteCleanup(), host_keys),
        host_keys,
    )
