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
from integration.test_remote_vm_disk import _base, _details, _vm
from nexora.app import create_app
from nexora.config import Settings
from nexora.remote.commands import CommandSpec
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.storage.contracts import StoragePoolCreateInput
from nexora.storage.volume_contracts import StorageVolumeCreateInput
from nexora.storage.volume_tasks import StorageVolumeTaskInput
from nexora.tasks.definitions import TaskCreate
from nexora.vms.contracts import VmChangeTaskInput

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="dedicated remote KVM integration environment is not configured",
)
VM_NAME = "nexora-it-existing"
ISO_NAME = "nexora-it-installer.iso"
ISO_PATH = f"{DIR_TARGET}/{ISO_NAME}"


def test_real_persistent_cdrom_eject_and_mount_local_iso(
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
        original = _remote(
            client,
            host_id,
            ("virsh", ("-c", "qemu:///system", "dumpxml", VM_NAME, "--inactive")),
        )
        pool: ResourceIndex | None = None
        try:
            _cleanup_iso(client, host_id)
            _cleanup_pool(client, host_id, DIR_NAME, DIR_TARGET)
            pool = _create_pool(
                client,
                StoragePoolCreateInput(host_id, DIR_NAME, "dir", DIR_TARGET),
            )
            volume = _create_iso(client, host_id, pool)
            _remote(
                client,
                host_id,
                (
                    "virsh",
                    (
                        "-c",
                        "qemu:///system",
                        "attach-disk",
                        VM_NAME,
                        ISO_PATH,
                        "hda",
                        "--type",
                        "cdrom",
                        "--mode",
                        "readonly",
                        "--config",
                    ),
                ),
            )
            client.app.state.domain_discovery_service.run(host_id)
            _accept_fixture_change(client, host_id)
            vm = _vm(client, host_id)
            cdrom = _cdrom(vm)
            _change(client, vm, volume, cdrom, "cdrom_eject")
            vm = _vm(client, host_id)
            assert _cdrom(vm)["source"] is None
            _change(client, vm, volume, _cdrom(vm), "cdrom_mount")
            assert ISO_PATH == _cdrom(_vm(client, host_id))["source"]
        finally:
            _remote(
                client,
                host_id,
                ("virsh", ("-c", "qemu:///system", "define", "/dev/stdin", "--validate")),
                stdin=original,
            )
            _cleanup_iso(client, host_id)
            if pool is not None:
                _delete_pool(client, pool)
            _remove_marker_and_target(client, host_id, DIR_TARGET)


def _create_iso(client: TestClient, host_id: str, pool: ResourceIndex) -> ResourceIndex:
    assert pool.persistent_hash is not None
    service = client.app.state.storage_volume_service
    preview = service.preview_create(
        StorageVolumeCreateInput(
            host_id,
            pool.id,
            pool.native_id,
            pool.observed_generation,
            pool.persistent_hash,
            ISO_NAME,
            "raw",
            1024**2,
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
            title="Create CD-ROM integration ISO",
            idempotency_scope=f"integration:cdrom:{pool.native_id}",
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
    client.app.state.storage_volume_service.discovery.run(host_id)
    with client.app.state.database.session() as session:
        volume = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == ResourceType.STORAGE_VOLUME,
                ResourceIndex.display_name == ISO_NAME,
            )
        )
        assert volume is not None
        return volume


def _change(
    client: TestClient,
    vm: ResourceIndex,
    volume: ResourceIndex,
    cdrom: dict[str, object],
    change_type: str,
) -> None:
    service = client.app.state.vm_cdrom_change_service
    if change_type == "cdrom_eject":
        preview = service.preview_eject(
            _base(vm),
            target=str(cdrom["target"]),
            bus=str(cdrom["bus"]),
            expected_source=str(cdrom["source"]),
        )
    else:
        preview = service.preview_mount(
            _base(vm),
            _base(volume),
            target=str(cdrom["target"]),
            bus=str(cdrom["bus"]),
            expected_source=None,
        )
    plan = service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id=vm.host_id,
        vm_uuid=vm.native_id,
        change_type=change_type,
    )
    task_input = VmChangeTaskInput(plan.id, vm.host_id, vm.native_id, change_type)
    task = client.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.cdrom_change",
            title=f"{change_type} integration ISO",
            idempotency_scope=f"integration:vm:{vm.native_id}:cdrom",
            idempotency_key=plan.id,
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


def _cdrom(vm: ResourceIndex) -> dict[str, object]:
    return next(
        disk
        for disk in _details(vm)["disks"]
        if disk["device"] == "cdrom" and disk["target"] == "hda"
    )


def _cleanup_iso(client: TestClient, host_id: str) -> None:
    client.app.state.remote_executor.run(
        host_id,
        CommandSpec(
            "virsh",
            ("-c", "qemu:///system", "vol-delete", ISO_NAME, "--pool", DIR_NAME),
        ),
        sudo=False,
        timeout=30,
    )


def _accept_fixture_change(client: TestClient, host_id: str) -> None:
    with client.app.state.database.session() as session:
        vm = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                ResourceIndex.display_name == VM_NAME,
            )
        )
        assert vm is not None
        vm.status = "managed"


def _remote(
    client: TestClient,
    host_id: str,
    command: tuple[str, tuple[str, ...]],
    *,
    stdin: bytes | None = None,
) -> bytes:
    result = client.app.state.remote_executor.run(
        host_id,
        CommandSpec(*command),
        sudo=False,
        timeout=60,
        stdin=stdin,
        sensitive=stdin is not None,
    )
    assert 0 == result.exit_code, result.stderr.decode(errors="replace")
    return result.stdout
