import json
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from web.test_vms import DOMAIN_UUID, _initialize, _seed_vm

from nexora.app import create_app
from nexora.config import Settings
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.web.security import CSRF_COOKIE

POOL_UUID = "22222222-2222-2222-2222-222222222222"
VOLUME_KEY = "/images/data.qcow2"


class DiskServiceStub:
    def preview_attach(
        self,
        vm_base: object,
        volume_base: object,
        *,
        bus: str,
        cache: str | None = None,
        io: str | None = None,
        discard: str | None = None,
        serial: str | None = None,
        readonly: bool = False,
        shareable: bool = False,
        live: bool = False,
    ) -> object:
        assert "virtio" == bus
        plan = SimpleNamespace(id="disk-plan", change_type="disk_attach", diff_text="+<disk>")
        return SimpleNamespace(plan=plan, confirmation_token="disk-confirmation")

    def preview_detach(
        self,
        vm_base: object,
        change: object,
        *,
        live: bool = False,
    ) -> object:
        plan = SimpleNamespace(id="disk-plan", change_type="disk_detach", diff_text="-<disk>")
        return SimpleNamespace(plan=plan, confirmation_token="disk-confirmation")

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
        change_type: str,
    ) -> object:
        assert ("disk-plan", "disk-confirmation") == (plan_id, token)
        assert "disk_attach" == change_type
        return SimpleNamespace(id=plan_id, change_type=change_type)


def test_disk_attach_preview_and_enqueue_via_internal_json(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        _seed_storage(client)
        client.app.state.vm_disk_change_service = DiskServiceStub()
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        preview = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/preview",
            headers=headers,
            json={
                "operation": "disk_attach",
                "values": {
                    "volume_resource_id": "volume-1",
                    "bus": "virtio",
                },
            },
        )
        assert 200 == preview.status_code
        payload = preview.json()
        assert "disk_attach" == payload["change_type"]
        assert "+<disk>" == payload["diff_text"]

        client.app.state.task_coordinator.stop()
        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/apply",
            headers=headers,
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
                "change_type": "disk_attach",
            },
        )
        assert 201 == response.status_code
        assert response.json()["location"].startswith("/tasks/")


def _seed_storage(client: TestClient) -> None:
    now = datetime.now(UTC)
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
                native_id=POOL_UUID,
                display_name="images",
                persistent_hash="a" * 64,
                details_json=json.dumps({"pool_type": "dir", "active": True}),
                **common,
            )
        )
        session.add(
            ResourceIndex(
                id="volume-1",
                resource_type=ResourceType.STORAGE_VOLUME,
                native_id=json.dumps([POOL_UUID, VOLUME_KEY], separators=(",", ":")),
                parent_native_id=POOL_UUID,
                display_name="data.qcow2",
                persistent_hash="b" * 64,
                details_json=json.dumps(
                    {
                        "key": VOLUME_KEY,
                        "path": VOLUME_KEY,
                        "format": "qcow2",
                        "capacity_bytes": 1024**3,
                    }
                ),
                **common,
            )
        )
