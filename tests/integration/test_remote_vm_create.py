import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from integration.test_remote_kvm import (
    _initialize,
    _onboard,
    _resource,
    _wait_for_task_types,
    _wait_task_id,
)
from nexora.app import create_app
from nexora.config import Settings
from nexora.remote.commands import CommandSpec
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.vms.creation_contracts import VmImportCreateInput
from nexora.vms.creation_tasks import VmCreationTaskInput

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="remote KVM VM creation integration environment is not configured",
)
VM_NAME = "nexora-it-import-create"
VM_UUID = "55ee0134-a825-4a64-9c33-b8c13a9861f5"
VOLUME_NAME = "nexora-it-import-create.qcow2"
ISO_NAME = "nexora-it-import-create.iso"


def test_create_vm_from_managed_volume_through_persistent_task(settings: Settings) -> None:
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
            _require_remote(
                client,
                host_id,
                CommandSpec(
                    "virsh",
                    (
                        "-c",
                        "qemu:///system",
                        "vol-create-as",
                        pool.native_id,
                        VOLUME_NAME,
                        "64M",
                        "--format",
                        "qcow2",
                    ),
                ),
            )
            _require_remote(
                client,
                host_id,
                CommandSpec(
                    "virsh",
                    (
                        "-c",
                        "qemu:///system",
                        "vol-create-as",
                        pool.native_id,
                        ISO_NAME,
                        "1M",
                        "--format",
                        "raw",
                    ),
                ),
            )
            client.app.state.storage_volume_service.discovery.run(host_id)
            volume = _volume(client, host_id, pool.native_id, VOLUME_NAME)
            iso = _volume(client, host_id, pool.native_id, ISO_NAME)
            create = _input(host_id, pool, volume, network, iso)
            preview = client.app.state.vm_creation_service.preview(create)
            plan = client.app.state.vm_creation_service.confirm(
                preview.plan.id,
                preview.confirmation_token,
                host_id=host_id,
                vm_uuid=VM_UUID,
            )
            task = client.app.state.task_queue.enqueue(
                TaskCreate(
                    task_type="vm.create",
                    title="Create integration VM",
                    idempotency_scope=f"integration:vm-create:{VM_UUID}",
                    idempotency_key=plan.id,
                    host_id=host_id,
                    vm_uuid=VM_UUID,
                    resource_type=ResourceType.VIRTUAL_MACHINE,
                    resource_id=VM_UUID,
                    total_steps=3,
                    recovery_strategy="verify_only",
                    input_summary=VmCreationTaskInput(plan.id, host_id, VM_UUID).encode(),
                )
            )
            _wait_task_id(client, task.id)
            _verify_and_start(client, host_id, network)
        finally:
            _cleanup(client, host_id, pool.native_id)


def _input(
    host_id: str,
    pool: ResourceIndex,
    volume: ResourceIndex,
    network: ResourceIndex,
    iso: ResourceIndex,
) -> VmImportCreateInput:
    details = json.loads(volume.details_json)
    assert pool.persistent_hash is not None
    assert volume.persistent_hash is not None
    assert network.persistent_hash is not None
    assert iso.persistent_hash is not None
    iso_details = json.loads(iso.details_json)
    return VmImportCreateInput(
        host_id=host_id,
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
        iso_resource_id=iso.id,
        iso_native_id=iso.native_id,
        iso_generation=iso.observed_generation,
        iso_hash=iso.persistent_hash,
        iso_key=str(iso_details["key"]),
        iso_name=iso.display_name,
    )


def _volume(
    client: TestClient,
    host_id: str,
    pool_uuid: str,
    name: str,
) -> ResourceIndex:
    with client.app.state.database.session() as session:
        volume = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == ResourceType.STORAGE_VOLUME,
                ResourceIndex.parent_native_id == pool_uuid,
                ResourceIndex.display_name == name,
            )
        )
        assert volume is not None
        session.expunge(volume)
        return volume


def _verify_and_start(
    client: TestClient,
    host_id: str,
    original_network: ResourceIndex,
) -> None:
    vm = _resource(client, host_id, ResourceType.VIRTUAL_MACHINE, VM_NAME)
    assert VM_UUID == vm.native_id
    details = json.loads(vm.details_json)
    assert "shut off" == str(details["state"]).lower()
    assert 512 * 1024 == details["memory_kib"]
    assert 1 == details["maximum_vcpus"]
    assert any(
        interface["type"] == "network"
        and interface["source"] == "default"
        and interface["model"] == "virtio"
        and interface["mac"]
        for interface in details["interfaces"]
    )
    assert any(
        disk["device"] == "cdrom"
        and disk["source"].endswith(ISO_NAME)
        and disk["bus"] == "sata"
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
    _require_remote(
        client,
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "destroy", VM_UUID)),
    )


def _cleanup(client: TestClient, host_id: str, pool_uuid: str) -> None:
    executor = client.app.state.remote_executor
    executor.run(
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "destroy", VM_UUID)),
        sudo=False,
        timeout=30,
    )
    executor.run(
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "undefine", VM_UUID)),
        sudo=False,
        timeout=30,
    )
    for name in (VOLUME_NAME, ISO_NAME):
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
    for name in (VOLUME_NAME, ISO_NAME):
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


def _require_remote(
    client: TestClient,
    host_id: str,
    command: CommandSpec,
) -> bytes:
    result = client.app.state.remote_executor.run(
        host_id,
        command,
        sudo=False,
        timeout=60,
    )
    assert 0 == result.exit_code, result.stderr.decode(errors="replace")
    assert not result.stdout_truncated
    assert not result.stderr_truncated
    return result.stdout
