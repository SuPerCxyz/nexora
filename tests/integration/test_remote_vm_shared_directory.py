import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from integration.test_remote_kvm import _initialize, _onboard, _resource, _wait_for_task_types
from nexora.app import create_app
from nexora.config import Settings
from nexora.remote.commands import CommandSpec
from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.xml import LibvirtXmlDocument

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
SHARE_ROOT = os.getenv("NEXORA_INTEGRATION_SHARED_DIRECTORY")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE or not SHARE_ROOT,
    reason="remote shared-directory integration environment is not configured",
)


def test_shared_directory_attach_detach_restores_vm_xml(settings: Settings) -> None:
    assert SHARE_ROOT == "/var/tmp/nexora-it-share"
    configured = settings.model_copy(update={"shared_directory_roots": SHARE_ROOT})
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(configured)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        vm = _resource(
            client,
            host_id,
            ResourceType.VIRTUAL_MACHINE,
            "nexora-it-existing",
        )
        service = client.app.state.vm_peripheral_change_service
        original = client.app.state.domain_discovery_service.read_one(host_id, vm.native_id)
        original_xml = original.documents["persistent_xml"]
        original_hash = original.persistent_hash
        assert original_hash is not None
        _require_remote(client, host_id, CommandSpec("mkdir", ("-m", "0755", "--", SHARE_ROOT)))
        try:
            _apply(client, service, vm, attach=True, task_id="integration-share-attach")
            attached = client.app.state.domain_discovery_service.read_one(host_id, vm.native_id)
            document = LibvirtXmlDocument.parse(
                attached.documents["persistent_xml"],
                expected_root="domain",
            )
            filesystem = document.root.find("./devices/filesystem")
            assert filesystem is not None
            assert filesystem.get("type") == "mount"
            assert filesystem.find("target").get("dir") == "nexora-share"

            current = _resource(
                client,
                host_id,
                ResourceType.VIRTUAL_MACHINE,
                "nexora-it-existing",
            )
            _apply(client, service, current, attach=False, task_id="integration-share-detach")
            restored = client.app.state.domain_discovery_service.read_one(host_id, vm.native_id)
            assert original_hash == restored.persistent_hash
        finally:
            _restore(client, host_id, vm.native_id, original_xml, original_hash)
            _require_remote(client, host_id, CommandSpec("rmdir", ("--", SHARE_ROOT)))


def _apply(
    client: TestClient,
    service: object,
    vm: ResourceIndex,
    *,
    attach: bool,
    task_id: str,
) -> None:
    preview = service.preview_shared_directory(  # type: ignore[attr-defined]
        _base(vm),
        root_index=0,
        target_tag="nexora-share",
        driver="virtiofs",
        readonly=True,
        attach=attach,
    )
    service.confirm(  # type: ignore[attr-defined]
        preview.plan.id,
        preview.confirmation_token,
        host_id=vm.host_id,
        vm_uuid=vm.native_id,
    )
    service.execute(preview.plan.id, task_id=task_id)  # type: ignore[attr-defined]


def _base(resource: ResourceIndex) -> ResourceBaseVersion:
    return ResourceBaseVersion(
        resource.id,
        resource.host_id,
        ResourceType(resource.resource_type),
        resource.native_id,
        resource.observed_generation,
        resource.persistent_hash,
        resource.live_hash,
    )


def _restore(
    client: TestClient,
    host_id: str,
    vm_uuid: str,
    original_xml: bytes,
    original_hash: str,
) -> None:
    current = client.app.state.domain_discovery_service.read_one(host_id, vm_uuid)
    if current.persistent_hash != original_hash:
        _require_remote(
            client,
            host_id,
            CommandSpec("virsh", ("-c", "qemu:///system", "define", "/dev/stdin", "--validate")),
            stdin=original_xml,
        )
    restored = client.app.state.domain_discovery_service.read_one(host_id, vm_uuid)
    assert original_hash == restored.persistent_hash


def _require_remote(
    client: TestClient,
    host_id: str,
    command: CommandSpec,
    *,
    stdin: bytes | None = None,
) -> None:
    result = client.app.state.remote_executor.run(
        host_id,
        command,
        sudo=False,
        timeout=30,
        stdin=stdin,
        env={"LC_ALL": "C"},
        sensitive=stdin is not None,
    )
    assert 0 == result.exit_code, result.stderr.decode(errors="replace")
