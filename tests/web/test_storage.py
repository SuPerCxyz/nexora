import json
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from nexora.app import create_app
from nexora.config import Settings
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.web.security import CSRF_COOKIE, PREAUTH_CSRF_COOKIE


class StorageServiceStub:
    def preview_create(self, create: object) -> object:
        plan = SimpleNamespace(
            id="plan-1",
            host_id="host-1",
            pool_uuid="11111111-1111-1111-1111-111111111111",
            pool_name="images",
            pool_type="dir",
            diff_text="+<pool type='dir'>",
        )
        return SimpleNamespace(plan=plan, confirmation_token="confirmation")

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        pool_uuid: str,
    ) -> object:
        assert ("plan-1", "confirmation") == (plan_id, token)
        assert "host-1" == host_id
        return SimpleNamespace(
            id=plan_id,
            host_id=host_id,
            pool_uuid=pool_uuid,
            pool_name="images",
        )


class VolumeMutationStub:
    def preview_delete(self, change: object) -> object:
        plan = SimpleNamespace(
            id="volume-plan",
            host_id="host-1",
            pool_uuid="11111111-1111-1111-1111-111111111111",
            volume_name="vm.qcow2",
            diff_text="-<volume>",
        )
        return SimpleNamespace(plan=plan, confirmation_token="volume-confirmation")

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        pool_uuid: str,
    ) -> object:
        assert ("volume-plan", "volume-confirmation") == (plan_id, token)
        return SimpleNamespace(
            id=plan_id,
            operation="delete",
            host_id=host_id,
            pool_uuid=pool_uuid,
            volume_name="vm.qcow2",
            volume_native_id=json.dumps([pool_uuid, "/images/vm.qcow2"]),
        )


class StorageVolumeServiceStub:
    def preview_create(self, create: object) -> object:
        plan = SimpleNamespace(
            id="volume-create-plan",
            host_id="host-1",
            pool_uuid="11111111-1111-1111-1111-111111111111",
            volume_name="data.qcow2",
            diff_text="+<volume>",
        )
        return SimpleNamespace(plan=plan, confirmation_token="volume-create-confirmation")

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        pool_uuid: str,
    ) -> object:
        assert ("volume-create-plan", "volume-create-confirmation") == (plan_id, token)
        return SimpleNamespace(
            id=plan_id,
            host_id=host_id,
            pool_uuid=pool_uuid,
            volume_name="data.qcow2",
        )


def test_internal_storage_previews_pool_and_volume_then_enqueues_tasks(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        _seed_storage(client)
        client.app.state.storage_pool_service = StorageServiceStub()
        client.app.state.storage_volume_service = StorageVolumeServiceStub()
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        overview = client.get("/internal/storage")
        assert 200 == overview.status_code
        assert "images" == overview.json()["pools"][0]["name"]
        assert "vm.qcow2" == overview.json()["volumes"][0]["name"]

        pool_preview = client.post(
            "/internal/storage/pools/preview",
            headers=headers,
            json={
                "host_id": "host-1",
                "name": "images",
                "pool_type": "dir",
                "target_path": "/var/lib/libvirt/images/custom",
            },
        )
        assert 200 == pool_preview.status_code
        assert "pool_create" == pool_preview.json()["operation"]

        volume_preview = client.post(
            "/internal/storage/volumes/preview",
            headers=headers,
            json={
                "pool_resource_id": "pool-1",
                "name": "data.qcow2",
                "volume_format": "qcow2",
                "capacity_gib": 20,
            },
        )
        assert 200 == volume_preview.status_code
        assert "volume_create" == volume_preview.json()["operation"]

        client.app.state.task_coordinator.stop()
        for path, preview in (
            ("/internal/storage/pools/apply", pool_preview.json()),
            ("/internal/storage/volumes/apply", volume_preview.json()),
        ):
            applied = client.post(
                path,
                headers=headers,
                json={
                    "plan_id": preview["plan_id"],
                    "confirmation_token": preview["confirmation_token"],
                    "host_id": preview["host_id"],
                    "pool_uuid": preview["pool_uuid"],
                },
            )
            assert 201 == applied.status_code
            assert applied.json()["location"].startswith("/tasks/")


def test_internal_storage_volume_delete_uses_json_preview(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        _seed_storage(client)
        client.app.state.storage_volume_mutation_service = VolumeMutationStub()
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        preview = client.post(
            "/internal/storage/mutations/preview",
            headers=headers,
            json={"resource_id": "volume-1", "operation": "volume_delete"},
        )
        assert 200 == preview.status_code
        assert "volume_delete" == preview.json()["operation"]
        client.app.state.task_coordinator.stop()
        response = client.post(
            "/internal/storage/mutations/apply",
            headers=headers,
            json={
                "plan_id": preview.json()["plan_id"],
                "confirmation_token": preview.json()["confirmation_token"],
                "host_id": preview.json()["host_id"],
                "pool_uuid": preview.json()["pool_uuid"],
                "operation": "volume_delete",
            },
        )
        assert 201 == response.status_code
        assert response.json()["location"].startswith("/tasks/")


def _initialize(client: TestClient) -> None:
    client.get("/initialize")
    response = client.post(
        "/initialize",
        data={
            "csrf_token": client.cookies.get(PREAUTH_CSRF_COOKIE),
            "username": "admin",
            "password": "VeryStrongPassword!123",
            "confirmation": "VeryStrongPassword!123",
        },
        follow_redirects=False,
    )
    assert 303 == response.status_code


def _seed_host(client: TestClient) -> None:
    now = datetime.now(UTC)
    with client.app.state.database.session() as session:
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


def _seed_storage(client: TestClient) -> None:
    now = datetime.now(UTC)
    pool_uuid = "11111111-1111-1111-1111-111111111111"
    common = {
        "host_id": "host-1",
        "status": ResourceStatus.MANAGED,
        "source": "existing",
        "observed_generation": 1,
        "labels_json": "[]",
        "first_seen_at": now,
        "last_seen_at": now,
    }
    with client.app.state.database.session() as session:
        session.add(
            ResourceIndex(
                id="pool-1",
                resource_type=ResourceType.STORAGE_POOL,
                native_id=pool_uuid,
                display_name="images",
                persistent_hash="a" * 64,
                details_json=json.dumps({"pool_type": "dir", "active": True, "state": "running"}),
                **common,
            )
        )
        session.add(
            ResourceIndex(
                id="volume-1",
                resource_type=ResourceType.STORAGE_VOLUME,
                native_id=json.dumps([pool_uuid, "/images/vm.qcow2"]),
                parent_native_id=pool_uuid,
                display_name="vm.qcow2",
                persistent_hash="b" * 64,
                details_json=json.dumps(
                    {
                        "key": "/images/vm.qcow2",
                        "path": "/images/vm.qcow2",
                        "format": "qcow2",
                        "capacity_bytes": 1024**3,
                    }
                ),
                **common,
            )
        )
