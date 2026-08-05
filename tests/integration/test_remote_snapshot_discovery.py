import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from integration.test_remote_kvm import (
    _initialize,
    _onboard,
    _wait_for_task_types,
)
from nexora.app import create_app
from nexora.config import Settings
from nexora.remote.commands import CommandSpec
from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceDocument, ResourceIndex, ResourceType
from nexora.resources.snapshot_discovery import SnapshotDiscoveryService
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.models import Task, TaskStatus
from nexora.vms.contracts import VmChangeTaskInput
from nexora.vms.snapshot_contracts import (
    SnapshotCreateInput,
    SnapshotDeleteInput,
    SnapshotRevertInput,
)

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="remote KVM snapshot integration environment is not configured",
)
VM_NAME = "nexora-it-snapshot-discovery"
VM_UUID = "74c301c0-5642-4255-9d4a-48002430cc91"
DISK_PATH = "/var/tmp/nexora-it-snapshot-discovery.qcow2"
SNAPSHOT_NAME = "before-upgrade"


def test_existing_snapshot_is_discovered_without_import(settings: Settings) -> None:
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        _cleanup(client, host_id)
        try:
            _create_fixture(client, host_id, with_snapshot=True)
            SnapshotDiscoveryService(
                client.app.state.database,
                client.app.state.remote_executor,
            ).run(host_id)
            with client.app.state.database.session() as session:
                snapshot = session.scalar(
                    select(ResourceIndex).where(
                        ResourceIndex.host_id == host_id,
                        ResourceIndex.resource_type == ResourceType.SNAPSHOT,
                        ResourceIndex.parent_native_id == VM_UUID,
                        ResourceIndex.display_name == SNAPSHOT_NAME,
                    )
                )
                assert snapshot is not None
                details = json.loads(snapshot.details_json)
                assert VM_UUID == details["domain_uuid"]
                assert "no" == details["memory"]
                assert any(item["snapshot"] == "internal" for item in details["disks"])
                document = session.scalar(
                    select(ResourceDocument).where(
                        ResourceDocument.resource_index_id == snapshot.id,
                        ResourceDocument.document_kind == "snapshot_xml",
                    )
                )
                assert document is not None and SNAPSHOT_NAME.encode() in document.content
        finally:
            _cleanup(client, host_id)


def test_nexora_creates_snapshot_through_persistent_task(settings: Settings) -> None:
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        _cleanup(client, host_id)
        try:
            _create_fixture(client, host_id, with_snapshot=False)
            _remote(
                client,
                host_id,
                CommandSpec(
                    "qemu-io",
                    ("-f", "qcow2", "-c", "write -P 0x11 0 4096", DISK_PATH),
                ),
            )
            client.app.state.domain_discovery_service.run(host_id)
            vm = _vm_resource(client, host_id)
            create = SnapshotCreateInput(
                ResourceBaseVersion(
                    vm.id,
                    host_id,
                    ResourceType.VIRTUAL_MACHINE,
                    vm.native_id,
                    vm.observed_generation,
                    str(vm.persistent_hash),
                    None,
                ),
                SNAPSHOT_NAME,
                "Created by Nexora integration test",
            )
            preview = client.app.state.vm_snapshot_service.preview_create(create)
            plan = client.app.state.vm_snapshot_service.confirm_create(
                preview.plan.id,
                preview.confirmation_token,
                host_id=host_id,
                vm_uuid=VM_UUID,
            )
            task = client.app.state.task_queue.enqueue(
                TaskCreate(
                    task_type="vm.snapshot_change",
                    title="Create integration Snapshot",
                    idempotency_scope=f"vm:{host_id}:{VM_UUID}:snapshot",
                    idempotency_key=plan.id,
                    host_id=host_id,
                    vm_uuid=VM_UUID,
                    resource_type=ResourceType.VIRTUAL_MACHINE,
                    resource_id=vm.id,
                    total_steps=3,
                    recovery_strategy="verify_only",
                    input_summary=VmChangeTaskInput(
                        plan.id,
                        host_id,
                        VM_UUID,
                        "snapshot_create",
                    ).encode(),
                )
            )
            _wait_for_snapshot_task(client, task.id)
            assert SNAPSHOT_NAME.encode() in _remote(
                client,
                host_id,
                CommandSpec(
                    "virsh",
                    ("-c", "qemu:///system", "snapshot-dumpxml", VM_NAME, SNAPSHOT_NAME),
                ),
            )
            snapshot = _snapshot_resource(client, host_id)
            _remote(
                client,
                host_id,
                CommandSpec(
                    "qemu-io",
                    ("-f", "qcow2", "-c", "write -P 0x22 0 4096", DISK_PATH),
                ),
            )
            revert = SnapshotRevertInput(
                create.vm_base,
                ResourceBaseVersion(
                    snapshot.id,
                    host_id,
                    ResourceType.SNAPSHOT,
                    snapshot.native_id,
                    snapshot.observed_generation,
                    str(snapshot.persistent_hash),
                    None,
                ),
                SNAPSHOT_NAME,
            )
            revert_preview = client.app.state.vm_snapshot_revert_service.preview(revert)
            revert_plan = client.app.state.vm_snapshot_revert_service.confirm(
                revert_preview.plan.id,
                revert_preview.confirmation_token,
                host_id=host_id,
                vm_uuid=VM_UUID,
                snapshot_name=SNAPSHOT_NAME,
                confirmation_name=VM_NAME,
            )
            revert_task = client.app.state.task_queue.enqueue(
                TaskCreate(
                    task_type="vm.snapshot_change",
                    title="Revert integration Snapshot",
                    idempotency_scope=f"vm:{host_id}:{VM_UUID}:snapshot",
                    idempotency_key=revert_plan.id,
                    host_id=host_id,
                    vm_uuid=VM_UUID,
                    resource_type=ResourceType.VIRTUAL_MACHINE,
                    resource_id=vm.id,
                    total_steps=3,
                    recovery_strategy="verify_only",
                    input_summary=VmChangeTaskInput(
                        revert_plan.id,
                        host_id,
                        VM_UUID,
                        "snapshot_revert",
                    ).encode(),
                )
            )
            _wait_for_snapshot_task(client, revert_task.id)
            _remote(
                client,
                host_id,
                CommandSpec(
                    "qemu-io",
                    ("-f", "qcow2", "-c", "read -P 0x11 0 4096", DISK_PATH),
                ),
            )
            delete = SnapshotDeleteInput(
                create.vm_base,
                ResourceBaseVersion(
                    snapshot.id,
                    host_id,
                    ResourceType.SNAPSHOT,
                    snapshot.native_id,
                    snapshot.observed_generation,
                    str(snapshot.persistent_hash),
                    None,
                ),
                SNAPSHOT_NAME,
            )
            delete_preview = client.app.state.vm_snapshot_delete_service.preview(delete)
            delete_plan = client.app.state.vm_snapshot_delete_service.confirm(
                delete_preview.plan.id,
                delete_preview.confirmation_token,
                host_id=host_id,
                vm_uuid=VM_UUID,
                snapshot_name=SNAPSHOT_NAME,
            )
            delete_task = client.app.state.task_queue.enqueue(
                TaskCreate(
                    task_type="vm.snapshot_change",
                    title="Delete integration Snapshot",
                    idempotency_scope=f"vm:{host_id}:{VM_UUID}:snapshot",
                    idempotency_key=delete_plan.id,
                    host_id=host_id,
                    vm_uuid=VM_UUID,
                    resource_type=ResourceType.VIRTUAL_MACHINE,
                    resource_id=vm.id,
                    total_steps=3,
                    recovery_strategy="verify_only",
                    input_summary=VmChangeTaskInput(
                        delete_plan.id,
                        host_id,
                        VM_UUID,
                        "snapshot_delete",
                    ).encode(),
                )
            )
            _wait_for_snapshot_task(client, delete_task.id)
            missing = client.app.state.remote_executor.run(
                host_id,
                CommandSpec(
                    "virsh",
                    ("-c", "qemu:///system", "snapshot-dumpxml", VM_NAME, SNAPSHOT_NAME),
                ),
                sudo=False,
                timeout=30,
            )
            assert missing.exit_code != 0
        finally:
            _cleanup(client, host_id)


def _create_fixture(
    client: TestClient,
    host_id: str,
    *,
    with_snapshot: bool,
) -> None:
    _remote(
        client,
        host_id,
        CommandSpec("qemu-img", ("create", "-f", "qcow2", DISK_PATH, "8M")),
    )
    xml = f"""<domain type='kvm'>
      <name>{VM_NAME}</name><uuid>{VM_UUID}</uuid>
      <memory unit='MiB'>128</memory><vcpu>1</vcpu>
      <os><type arch='x86_64' machine='pc'>hvm</type></os>
      <devices><disk type='file' device='disk'>
        <driver name='qemu' type='qcow2'/>
        <source file='{DISK_PATH}'/><target dev='vda' bus='virtio'/>
      </disk></devices></domain>""".encode()
    _remote(
        client,
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "define", "/dev/stdin", "--validate")),
        stdin=xml,
    )
    if with_snapshot:
        _remote(
            client,
            host_id,
            CommandSpec(
                "virsh",
                (
                    "-c",
                    "qemu:///system",
                    "snapshot-create-as",
                    VM_NAME,
                    SNAPSHOT_NAME,
                    "Nexora discovery fixture",
                    "--atomic",
                ),
            ),
        )


def _vm_resource(client: TestClient, host_id: str) -> ResourceIndex:
    with client.app.state.database.session() as session:
        vm = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                ResourceIndex.native_id == VM_UUID,
            )
        )
        if vm is None:
            raise AssertionError("integration fixture VM was not discovered")
        session.expunge(vm)
        return vm


def _snapshot_resource(client: TestClient, host_id: str) -> ResourceIndex:
    with client.app.state.database.session() as session:
        snapshot = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == ResourceType.SNAPSHOT,
                ResourceIndex.display_name == SNAPSHOT_NAME,
                ResourceIndex.status != "missing",
            )
        )
        if snapshot is None:
            raise AssertionError("created integration Snapshot was not indexed")
        session.expunge(snapshot)
        return snapshot


def _wait_for_snapshot_task(client: TestClient, task_id: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with client.app.state.database.session() as session:
            task = session.get(Task, task_id)
            if task is not None and task.status == TaskStatus.SUCCEEDED:
                return
            if task is not None and task.status == TaskStatus.FAILED:
                raise AssertionError(task.error_message)
        time.sleep(0.05)
    raise AssertionError("Snapshot task did not complete")


def _cleanup(client: TestClient, host_id: str) -> None:
    executor = client.app.state.remote_executor
    executor.run(
        host_id,
        CommandSpec(
            "virsh",
            ("-c", "qemu:///system", "snapshot-delete", VM_NAME, SNAPSHOT_NAME),
        ),
        sudo=False,
        timeout=60,
    )
    executor.run(
        host_id,
        CommandSpec(
            "virsh",
            ("-c", "qemu:///system", "undefine", VM_NAME, "--snapshots-metadata"),
        ),
        sudo=False,
        timeout=30,
    )
    remaining = executor.run(
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "dominfo", VM_NAME)),
        sudo=False,
        timeout=30,
    )
    if remaining.exit_code == 0:
        raise AssertionError("snapshot discovery fixture VM cleanup failed")
    executor.run(
        host_id,
        CommandSpec("rm", ("-f", "--", DISK_PATH)),
        sudo=False,
        timeout=30,
    )
    disk_check = executor.run(
        host_id,
        CommandSpec("test", ("!", "-e", DISK_PATH)),
        sudo=False,
        timeout=30,
    )
    if disk_check.exit_code != 0:
        raise AssertionError("snapshot fixture disk cleanup failed")


def _remote(
    client: TestClient,
    host_id: str,
    command: CommandSpec,
    *,
    stdin: bytes | None = None,
) -> bytes:
    result = client.app.state.remote_executor.run(
        host_id,
        command,
        sudo=False,
        timeout=60,
        stdin=stdin,
        sensitive=stdin is not None,
    )
    assert 0 == result.exit_code, result.stderr.decode(errors="replace")
    return result.stdout
