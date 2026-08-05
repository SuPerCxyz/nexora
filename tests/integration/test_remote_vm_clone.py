import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
from nexora.resources.models import ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.vms.clone_contracts import VmCloneManifest
from nexora.vms.clone_tasks import VmCloneTaskInput

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="remote KVM clone integration environment is not configured",
)
SOURCE_NAME = "nexora-it-clone-source"
SOURCE_UUID = "a2602922-893f-45d5-bd20-1e0b237a22c1"
TARGET_NAME = "nexora-it-clone-target"


def test_shutdown_full_clone_through_persistent_task(settings: Settings) -> None:
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
        target_dir = str(json.loads(pool.details_json)["target_path"])
        source_disk = f"{target_dir}/{SOURCE_NAME}.qcow2"
        _cleanup(client, host_id, source_disk, target_dir)
        try:
            _prepare_source(client, host_id, source_disk)
            client.app.state.domain_discovery_service.run(host_id)
            source = _resource(client, host_id, ResourceType.VIRTUAL_MACHINE, SOURCE_NAME)
            assert source.persistent_hash is not None
            preview = client.app.state.vm_clone_service.preview(
                source_host_id=host_id,
                source_vm_uuid=SOURCE_UUID,
                source_resource_id=source.id,
                source_generation=source.observed_generation,
                source_hash=source.persistent_hash,
                target_pool_id=pool.id,
                target_name=TARGET_NAME,
            )
            plan = client.app.state.vm_clone_service.confirm(
                preview.plan.id,
                preview.confirmation_token,
                source_host_id=host_id,
                source_vm_uuid=SOURCE_UUID,
            )
            manifest = preview.manifest
            task_input = VmCloneTaskInput(
                plan.id,
                host_id,
                SOURCE_UUID,
                host_id,
                manifest.target_vm_uuid,
            )
            task = client.app.state.task_queue.enqueue(
                TaskCreate(
                    task_type="vm.clone",
                    title="Clone integration VM",
                    idempotency_scope=f"integration:clone:{SOURCE_UUID}",
                    idempotency_key=plan.id,
                    host_id=host_id,
                    vm_uuid=SOURCE_UUID,
                    total_steps=len(manifest.files) + 3,
                    resumable=True,
                    recovery_strategy="resume_from_checkpoint",
                    input_summary=task_input.encode(),
                )
            )
            _wait_task_id(client, task.id)
            _verify(client, host_id, manifest.target_vm_uuid, source_disk, manifest)
        finally:
            _cleanup(client, host_id, source_disk, target_dir)


def _prepare_source(client: TestClient, host_id: str, disk_path: str) -> None:
    _require(
        client,
        host_id,
        CommandSpec("qemu-img", ("create", "-f", "qcow2", disk_path, "32M")),
    )
    xml = f"""<domain type="kvm">
<name>{SOURCE_NAME}</name><uuid>{SOURCE_UUID}</uuid>
<memory unit="MiB">256</memory><vcpu>1</vcpu>
<os><type arch="x86_64">hvm</type><boot dev="hd"/></os>
<metadata><nexora-test preserve="yes"/></metadata>
<devices>
<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>
<source file="{disk_path}"/><target dev="vda" bus="virtio"/></disk>
<interface type="network"><mac address="52:54:00:11:22:33"/>
<source network="default"/><model type="virtio"/></interface>
<serial type="pty"/><console type="pty"/>
</devices></domain>""".encode()
    result = client.app.state.remote_executor.run(
        host_id,
        CommandSpec(
            "virsh",
            ("-c", "qemu:///system", "define", "/dev/stdin", "--validate"),
        ),
        sudo=False,
        timeout=30,
        stdin=xml,
        sensitive=True,
    )
    assert 0 == result.exit_code


def _verify(
    client: TestClient,
    host_id: str,
    target_uuid: str,
    source_disk: str,
    manifest: VmCloneManifest,
) -> None:
    target = _resource(client, host_id, ResourceType.VIRTUAL_MACHINE, TARGET_NAME)
    assert target_uuid == target.native_id
    details = json.loads(target.details_json)
    assert not details["active"]
    target_disk = next(item["source"] for item in details["disks"] if item["device"] == "disk")
    assert source_disk != target_disk
    source_hash = _require(client, host_id, CommandSpec("sha256sum", ("--", source_disk))).split()[
        0
    ]
    target_hash = _require(
        client, host_id, CommandSpec("sha256sum", ("--", str(target_disk)))
    ).split()[0]
    assert source_hash == target_hash
    _require(
        client,
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "start", target_uuid)),
    )
    _require(
        client,
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "destroy", target_uuid)),
    )
    assert not any(
        client.app.state.remote_executor.run(
            host_id,
            CommandSpec("test", ("-e", item.partial_path)),
            sudo=False,
            timeout=10,
        ).exit_code
        == 0
        for item in manifest.files
    )


def _cleanup(
    client: TestClient,
    host_id: str,
    source_disk: str,
    target_dir: str,
) -> None:
    for identity in (SOURCE_UUID, SOURCE_NAME, TARGET_NAME):
        client.app.state.remote_executor.run(
            host_id,
            CommandSpec(
                "virsh",
                ("-c", "qemu:///system", "destroy", identity),
            ),
            sudo=False,
            timeout=20,
        )
        client.app.state.remote_executor.run(
            host_id,
            CommandSpec(
                "virsh",
                ("-c", "qemu:///system", "undefine", identity, "--nvram"),
            ),
            sudo=False,
            timeout=20,
        )
    patterns = (
        source_disk,
        f"{target_dir}/{TARGET_NAME}-disk1.qcow2",
    )
    for path in patterns:
        client.app.state.remote_executor.run(
            host_id,
            CommandSpec("rm", ("-f", "--", path)),
            sudo=False,
            timeout=20,
        )
    client.app.state.remote_executor.run(
        host_id,
        CommandSpec(
            "find",
            (
                target_dir,
                "-maxdepth",
                "1",
                "-type",
                "f",
                "-name",
                f".{TARGET_NAME}-disk1.qcow2.nexora-*.partial",
                "-delete",
            ),
        ),
        sudo=False,
        timeout=20,
    )


def _require(client: TestClient, host_id: str, command: CommandSpec) -> bytes:
    result = client.app.state.remote_executor.run(
        host_id,
        command,
        sudo=False,
        timeout=60,
    )
    assert 0 == result.exit_code, result.stderr.decode(errors="replace")
    return result.stdout
