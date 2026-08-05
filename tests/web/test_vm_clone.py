from types import SimpleNamespace

from fastapi.testclient import TestClient
from web.test_storage import _seed_storage
from web.test_vms import DOMAIN_UUID, _initialize, _seed_vm

from nexora.app import create_app
from nexora.config import Settings
from nexora.vms.clone_contracts import CloneFile, VmCloneManifest
from nexora.web.security import CSRF_COOKIE


class CloneServiceStub:
    def __init__(self) -> None:
        self.manifest = VmCloneManifest(
            source_host_id="host-1",
            source_vm_uuid=DOMAIN_UUID,
            source_generation=1,
            source_hash="a" * 64,
            target_host_id="host-1",
            target_pool_id="pool-1",
            target_pool_uuid="11111111-1111-1111-1111-111111111111",
            target_pool_generation=1,
            target_pool_hash="b" * 64,
            target_vm_uuid="33333333-3333-3333-3333-333333333333",
            target_name="guest-clone",
            mac_addresses=("52:54:00:aa:bb:cc",),
            files=(
                CloneFile(
                    "/images/guest.qcow2",
                    "/images/guest-clone-disk1.qcow2",
                    "/images/.guest-clone.partial",
                    4096,
                    "disk",
                ),
            ),
        )

    def preview(self, **request: object) -> object:
        assert "guest-clone" == request["target_name"]
        plan = SimpleNamespace(
            id="clone-plan",
            source_host_id="host-1",
            source_vm_uuid=DOMAIN_UUID,
            target_name="guest-clone",
            diff_text="- source\n+ clone",
        )
        return SimpleNamespace(
            plan=plan,
            manifest=self.manifest,
            confirmation_token="confirmation",
        )

    def confirm(self, *args: object, **kwargs: object) -> object:
        assert ("clone-plan", "confirmation") == args
        return SimpleNamespace(
            id="clone-plan",
            target_name="guest-clone",
            manifest_json=self.manifest.encode(),
        )


def test_internal_shutdown_clone_returns_json_task(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        _seed_storage(client)
        client.app.state.vm_clone_service = CloneServiceStub()
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        preview = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/clone/preview",
            headers=headers,
            json={"target_pool_id": "pool-1", "target_name": "guest-clone"},
        )
        assert 200 == preview.status_code
        assert "guest-clone" == preview.json()["target_name"]
        client.app.state.task_coordinator.stop()
        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/clone/apply",
            headers=headers,
            json={
                "plan_id": preview.json()["plan_id"],
                "confirmation_token": preview.json()["confirmation_token"],
            },
        )
        assert 201 == response.status_code
        assert response.json()["location"].startswith("/tasks/")


class MigrationServiceStub:
    def __init__(self) -> None:
        self.manifest = VmCloneManifest(
            source_host_id="host-1",
            source_vm_uuid=DOMAIN_UUID,
            source_generation=1,
            source_hash="a" * 64,
            target_host_id="host-1",
            target_pool_id="pool-1",
            target_pool_uuid="11111111-1111-1111-1111-111111111111",
            target_pool_generation=1,
            target_pool_hash="b" * 64,
            target_vm_uuid=DOMAIN_UUID,
            target_name="existing-vm",
            mac_addresses=("52:54:00:aa:bb:cc",),
            files=(
                CloneFile(
                    "/images/guest.qcow2",
                    "/images/guest-disk1.qcow2",
                    "/images/.guest.partial",
                    4096,
                    "disk",
                ),
            ),
            preserve_identity=True,
        )

    def preview(self, **request: object) -> object:
        assert request["preserve_identity"] is True
        assert "existing-vm" == request["target_name"]
        plan = SimpleNamespace(
            id="migrate-plan",
            source_host_id="host-1",
            source_vm_uuid=DOMAIN_UUID,
            target_name="existing-vm",
            diff_text="- source\n+ migrated",
        )
        return SimpleNamespace(
            plan=plan,
            manifest=self.manifest,
            confirmation_token="migration-confirmation",
        )

    def confirm(self, *args: object, **kwargs: object) -> object:
        assert ("migrate-plan", "migration-confirmation") == args
        return SimpleNamespace(
            id="migrate-plan",
            target_name="existing-vm",
            manifest_json=self.manifest.encode(),
        )


def test_internal_shutdown_migrate_preserves_identity(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        _seed_storage(client)
        client.app.state.vm_clone_service = MigrationServiceStub()
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        preview = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/migrate/preview",
            headers=headers,
            json={"target_pool_id": "pool-1"},
        )
        assert 200 == preview.status_code
        payload = preview.json()
        assert payload["preserve_identity"] is True
        assert DOMAIN_UUID == payload["target_vm_uuid"]
        assert "existing-vm" == payload["target_name"]
        client.app.state.task_coordinator.stop()
        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/migrate/apply",
            headers=headers,
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
            },
        )
        assert 201 == response.status_code
        assert response.json()["location"].startswith("/tasks/")


def test_internal_migrate_rejects_non_identity_plan(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        _seed_storage(client)
        stub = CloneServiceStub()
        client.app.state.vm_clone_service = stub
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        client.app.state.task_coordinator.stop()
        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/migrate/apply",
            headers=headers,
            json={
                "plan_id": "clone-plan",
                "confirmation_token": "confirmation",
            },
        )
        assert 409 == response.status_code
        assert "身份不匹配" in response.json()["message"]
