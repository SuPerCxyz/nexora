import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from integration.platform_iso_support import (
    index_media,
    media_file,
    start_media_server,
    stop_server,
)
from integration.test_remote_kvm import (
    _initialize,
    _onboard,
    _wait_for_task_types,
    _wait_task,
)
from nexora.app import create_app
from nexora.config import Settings
from nexora.media.iso_cache import MediaIsoCache
from nexora.remote.commands import CommandSpec
from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.vms.contracts import VmChangeTaskInput
from nexora.vms.cpu_changes import VmChangeConflict

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
MEDIA_BASE_URL = os.getenv("NEXORA_INTEGRATION_MEDIA_BASE_URL")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE or not MEDIA_BASE_URL,
    reason="remote KVM platform media integration environment is not configured",
)
VM_NAME = "nexora-it-platform-iso"
VM_UUID = "9b449715-7f61-459c-a9f7-e6f87bb48ab1"


def test_platform_iso_range_and_remote_cache_fallback(settings: Settings) -> None:
    origin = urlsplit(MEDIA_BASE_URL or "")
    assert origin.scheme == "http" and origin.hostname and origin.port
    media = media_file(settings.library_dir)
    runtime = settings.model_copy(update={"media_public_base_url": MEDIA_BASE_URL})
    private_key = Path(KEY_FILE or "").read_text()
    server: subprocess.Popen[bytes] | None = None
    with TestClient(create_app(runtime)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        _remote_cleanup(client, host_id)
        cache_path: str | None = None
        try:
            _define_fixture(client, host_id)
            client.app.state.domain_discovery_service.run(host_id)
            vm = _vm(client, host_id)
            item = index_media(client, media)
            server = start_media_server(runtime, origin)
            _verify_source_bound_range(client, host_id, item.id)
            with pytest.raises(VmChangeConflict, match="cache fallback"):
                client.app.state.vm_platform_iso_service.preview_platform_mount(
                    _base(vm),
                    item.id,
                    target="hda",
                    bus="ide",
                    expected_source=None,
                )
            service = client.app.state.vm_cached_iso_service
            preview = service.preview_cached_mount(
                _base(vm),
                item.id,
                target="hda",
                bus="ide",
                expected_source=None,
            )
            plan = service.confirm(
                preview.plan.id,
                preview.confirmation_token,
                host_id=host_id,
                vm_uuid=vm.native_id,
                change_type="cdrom_cache_mount",
            )
            _execute(client, vm, plan.id, "cdrom_cache_mount")
            cache_path = MediaIsoCache.path_for(item.sha256)
            assert item.sha256.encode() in _remote(
                client,
                host_id,
                CommandSpec("sha256sum", ("--", cache_path)),
            )
            _remote(
                client,
                host_id,
                CommandSpec("virsh", ("-c", "qemu:///system", "start", VM_NAME)),
            )
            _remote(
                client,
                host_id,
                CommandSpec("virsh", ("-c", "qemu:///system", "destroy", VM_NAME)),
            )
            client.app.state.domain_discovery_service.run(host_id)
            vm = _vm(client, host_id)
            source = _cdrom_source(vm)
            assert cache_path == source
            preview = service.preview_cached_eject(
                _base(vm),
                target="hda",
                bus="ide",
                expected_source=source,
            )
            plan = service.confirm(
                preview.plan.id,
                preview.confirmation_token,
                host_id=host_id,
                vm_uuid=vm.native_id,
                change_type="cdrom_cache_eject",
            )
            _execute(client, vm, plan.id, "cdrom_cache_eject")
            _assert_remote_absent(client, host_id, cache_path)
        finally:
            _remote_cleanup(client, host_id, cache_path)
            if server is not None:
                stop_server(server)


def _define_fixture(client: TestClient, host_id: str) -> None:
    xml = f"""<domain type='kvm'>
      <name>{VM_NAME}</name><uuid>{VM_UUID}</uuid>
      <memory unit='MiB'>128</memory><vcpu>1</vcpu>
      <os><type arch='x86_64' machine='pc'>hvm</type><boot dev='cdrom'/></os>
      <devices><disk type='file' device='cdrom'>
        <driver name='qemu' type='raw'/><target dev='hda' bus='ide' tray='open'/>
        <readonly/>
      </disk><graphics type='vnc' autoport='yes' listen='127.0.0.1'/>
      </devices></domain>""".encode()
    _remote(
        client,
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "define", "/dev/stdin", "--validate")),
        stdin=xml,
    )


def _vm(client: TestClient, host_id: str) -> ResourceIndex:
    with client.app.state.database.session() as session:
        vm = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                ResourceIndex.native_id == VM_UUID,
                ResourceIndex.status == ResourceStatus.MANAGED,
            )
        )
        assert vm is not None
        return vm


def _base(vm: ResourceIndex) -> ResourceBaseVersion:
    return ResourceBaseVersion(
        vm.id,
        vm.host_id,
        ResourceType.VIRTUAL_MACHINE,
        vm.native_id,
        vm.observed_generation,
        vm.persistent_hash,
        vm.live_hash,
    )


def _execute(
    client: TestClient,
    vm: ResourceIndex,
    plan_id: str,
    change_type: str,
) -> None:
    value = VmChangeTaskInput(plan_id, vm.host_id, vm.native_id, change_type)
    task = client.app.state.task_queue.enqueue(
        TaskCreate(
            task_type="vm.cached_iso_change",
            title=f"{change_type} integration",
            idempotency_scope=f"integration:vm:{vm.native_id}:cached-iso",
            idempotency_key=plan_id,
            host_id=vm.host_id,
            vm_uuid=vm.native_id,
            resource_type=ResourceType.VIRTUAL_MACHINE,
            resource_id=vm.id,
            total_steps=8 if change_type == "cdrom_cache_mount" else 3,
            resumable=False,
            recovery_strategy="verify_only",
            input_summary=value.encode(),
        )
    )
    _wait_task(client, task)


def _cdrom_source(vm: ResourceIndex) -> str:
    import json

    details = json.loads(vm.details_json)
    source = next(
        disk["source"]
        for disk in details["disks"]
        if disk["device"] == "cdrom" and disk["target"] == "hda"
    )
    assert isinstance(source, str)
    return source


def _verify_source_bound_range(
    client: TestClient,
    host_id: str,
    media_item_id: str,
) -> None:
    credentials = client.app.state.media_credential_service
    credential = credentials.issue_for_node(
        media_item_id,
        host_id=host_id,
        vm_uuid=VM_UUID,
    )
    url = f"{MEDIA_BASE_URL}/media/content/{credential.id}"
    content = _remote(
        client,
        host_id,
        CommandSpec(
            "curl",
            ("--fail", "--silent", "--show-error", "--range", "0-15", url),
        ),
    )
    assert 16 == len(content)
    assert credentials.revoke(credential.id) is True
    rejected = client.app.state.remote_executor.run(
        host_id,
        CommandSpec("curl", ("--fail", "--silent", "--range", "0-15", url)),
        sudo=False,
        timeout=30,
    )
    assert 22 == rejected.exit_code


def _assert_remote_absent(client: TestClient, host_id: str, path: str) -> None:
    result = client.app.state.remote_executor.run(
        host_id,
        CommandSpec("test", ("-e", path)),
        sudo=False,
        timeout=30,
    )
    assert 1 == result.exit_code


def _remote_cleanup(
    client: TestClient,
    host_id: str,
    cache_path: str | None = None,
) -> None:
    client.app.state.remote_executor.run(
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "destroy", VM_NAME)),
        sudo=False,
        timeout=30,
    )
    if cache_path is not None:
        client.app.state.remote_executor.run(
            host_id,
            CommandSpec("rm", ("-f", "--", cache_path)),
            sudo=False,
            timeout=30,
        )
    client.app.state.remote_executor.run(
        host_id,
        CommandSpec("virsh", ("-c", "qemu:///system", "undefine", VM_NAME)),
        sudo=False,
        timeout=30,
    )


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
