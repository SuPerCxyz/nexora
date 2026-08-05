import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from web.test_storage import _seed_host, _seed_storage
from web.test_vm_create import _seed_iso, _seed_network
from web.test_vms import _initialize

from nexora.app import create_app
from nexora.config import Settings
from nexora.vms.blank_creation_contracts import VmBlankCreateInput
from nexora.web.security import CSRF_COOKIE


class BlankCreationServiceStub:
    def __init__(self) -> None:
        self.create: VmBlankCreateInput | None = None

    def preview(self, create: object) -> object:
        if isinstance(create, VmBlankCreateInput):
            self.create = create
        plan = SimpleNamespace(id="blank-plan", diff_text="+ <domain/>")
        return SimpleNamespace(plan=plan, confirmation_token="confirmation")

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
    ) -> object:
        assert ("blank-plan", "confirmation") == (plan_id, token)
        return SimpleNamespace(
            id=plan_id,
            host_id=host_id,
            vm_uuid=vm_uuid,
            vm_name="blank-vm",
        )


def test_internal_blank_create_preview_requires_csrf_and_creates_task(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        _seed_storage(client)
        _seed_network(client)
        _seed_iso(client)
        with client.app.state.database.session() as session:
            from nexora.resources.models import ResourceIndex

            pool = session.get(ResourceIndex, "pool-1")
            assert pool is not None
            pool.details_json = json.dumps(
                {
                    "pool_type": "dir",
                    "active": True,
                    "state": "running",
                    "target_path": "/images",
                }
            )
        service = BlankCreationServiceStub()
        client.app.state.vm_blank_creation_service = service
        submitted = {
            "name": "blank-vm",
            "memory_mib": 2048,
            "vcpus": 2,
            "pool_resource_id": "pool-1",
            "disk_name": "blank.qcow2",
            "volume_format": "qcow2",
            "capacity_gib": 20,
            "network_resource_id": "network-1",
            "iso_resource_id": "iso-1",
            "firmware": "uefi",
            "secure_boot": False,
            "tpm2": True,
        }

        assert (
            403 == client.post("/internal/vm-create/blank-disk/preview", json=submitted).status_code
        )
        headers = {"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)}
        preview = client.post(
            "/internal/vm-create/blank-disk/preview",
            json=submitted,
            headers=headers,
        )

        assert 200 == preview.status_code
        payload = preview.json()
        assert "blank.qcow2" == payload["summary"]["disk_name"]
        assert 20 * 1024**3 == payload["summary"]["capacity_bytes"]
        assert "default" in payload["summary"]["network"]
        assert payload["summary"]["iso_name"] == "install.iso"
        assert payload["summary"]["secure_boot"] is False
        assert "+ <domain/>" == payload["diff_text"]
        assert service.create is not None
        assert "network" == service.create.network_kind
        assert "install.iso" == service.create.iso_name
        assert service.create.tpm2

        client.app.state.task_coordinator.stop()
        applied = client.post(
            "/internal/vm-create/blank-disk/apply",
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
                "host_id": payload["host_id"],
                "vm_uuid": payload["vm_uuid"],
            },
            headers=headers,
        )
        assert 201 == applied.status_code
        assert applied.json()["location"].startswith("/tasks/")


def test_internal_blank_create_options_lists_writable_pools(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        _seed_storage(client)
        with client.app.state.database.session() as session:
            from nexora.resources.models import ResourceIndex

            pool = session.get(ResourceIndex, "pool-1")
            assert pool is not None
            pool.details_json = json.dumps(
                {
                    "pool_type": "dir",
                    "active": True,
                    "state": "running",
                    "target_path": "/images",
                }
            )

        options = client.get("/internal/vm-create/blank-disk/options")
        assert 200 == options.status_code
        payload = options.json()
        assert any(item["id"] == "pool-1" for item in payload["pools"])
