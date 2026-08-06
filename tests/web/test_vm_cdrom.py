import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from web.test_vm_disks import _seed_storage
from web.test_vms import DOMAIN_UUID, _initialize, _seed_vm

from nexora.app import create_app
from nexora.config import Settings
from nexora.resources.models import ResourceIndex
from nexora.web.security import CSRF_COOKIE


class CdromServiceStub:
    def preview_mount(
        self,
        vm_base: object,
        volume_base: object,
        *,
        target: str,
        bus: str,
        expected_source: str | None,
        live: bool = False,
    ) -> object:
        assert ("sda", "sata", None) == (target, bus, expected_source)
        plan = SimpleNamespace(
            id="cdrom-plan", change_type="cdrom_mount", diff_text="+<source file='installer.iso'>"
        )
        return SimpleNamespace(plan=plan, confirmation_token="cdrom-confirmation")

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
        change_type: str,
    ) -> object:
        assert ("cdrom-plan", "cdrom-confirmation") == (plan_id, token)
        assert "cdrom_mount" == change_type
        return SimpleNamespace(id=plan_id, change_type=change_type)


def test_local_iso_requires_preview_then_enqueues_cdrom_task(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        vm = _seed_vm(client)
        _seed_storage(client)
        with client.app.state.database.session() as session:
            stored_vm = session.get(ResourceIndex, vm.id)
            volume = session.get(ResourceIndex, "volume-1")
            assert stored_vm is not None and volume is not None
            details = json.loads(stored_vm.details_json)
            details["disks"] = [
                {
                    "device": "cdrom",
                    "target": "sda",
                    "bus": "sata",
                    "source": None,
                }
            ]
            stored_vm.details_json = json.dumps(details)
            volume.display_name = "installer.iso"
            volume_details = json.loads(volume.details_json)
            volume_details.update(
                path="/images/installer.iso",
                key="/images/installer.iso",
                format="raw",
            )
            volume.details_json = json.dumps(volume_details)
        client.app.state.vm_cdrom_change_service = CdromServiceStub()
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        preview = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/preview",
            headers=headers,
            json={
                "operation": "cdrom_mount",
                "values": {
                    "volume_resource_id": "volume-1",
                    "target": "sda",
                    "bus": "sata",
                    "expected_source": "",
                },
            },
        )
        assert 200 == preview.status_code
        payload = preview.json()
        assert "cdrom_mount" == payload["change_type"]
        assert "+<source file='installer.iso'>" == payload["diff_text"]

        client.app.state.task_coordinator.stop()
        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/apply",
            headers=headers,
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
                "change_type": "cdrom_mount",
            },
        )
        assert 201 == response.status_code
        assert response.json()["location"].startswith("/tasks/")
