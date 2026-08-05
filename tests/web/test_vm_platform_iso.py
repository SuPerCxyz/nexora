import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select
from web.test_vms import DOMAIN_UUID, _initialize, _seed_vm

from nexora.app import create_app
from nexora.media.store import MediaObservation
from nexora.resources.models import ResourceIndex
from nexora.web.security import CSRF_COOKIE


class PlatformIsoStub:
    def preview_platform_mount(
        self,
        vm_base: object,
        media_item_id: str,
        *,
        target: str,
        bus: str,
        expected_source: str | None,
    ) -> object:
        assert media_item_id
        assert ("sda", "sata", None) == (target, bus, expected_source)
        plan = SimpleNamespace(
            id="platform-plan",
            change_type="cdrom_platform_mount",
            diff_text="+<source protocol='http'>",
        )
        return SimpleNamespace(plan=plan, confirmation_token="platform-confirmation")

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
        change_type: str,
    ) -> object:
        assert ("platform-plan", "platform-confirmation") == (plan_id, token)
        assert "cdrom_platform_mount" == change_type
        return SimpleNamespace(id=plan_id, change_type=change_type)


def test_platform_iso_preview_enqueues_source_bound_task(settings) -> None:
    runtime = settings.model_copy(
        update={"media_public_base_url": "http://nexora.example.test:8000"}
    )
    with TestClient(create_app(runtime)) as client:
        _initialize(client)
        _seed_vm(client)
        with client.app.state.database.session() as session:
            stored = session.scalar(
                select(ResourceIndex).where(ResourceIndex.resource_type == "virtual_machine")
            )
            assert stored is not None
            details = json.loads(stored.details_json)
            details["disks"] = [
                {"type": "file", "device": "cdrom", "target": "sda", "bus": "sata", "source": None}
            ]
            stored.details_json = json.dumps(details)
        scan = client.app.state.media_index_store.begin()
        client.app.state.media_index_store.complete(
            scan.id,
            [
                MediaObservation(
                    "iso/linux.iso",
                    "linux.iso",
                    "iso",
                    1024,
                    1,
                    1,
                    1,
                    "c" * 64,
                    None,
                    None,
                    (),
                    "linux_iso",
                    "x86_64",
                )
            ],
        )
        item = client.app.state.media_index_store.list_items()[0]
        client.app.state.vm_platform_iso_service = PlatformIsoStub()
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        preview = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/preview",
            headers=headers,
            json={
                "operation": "platform_iso_mount",
                "values": {
                    "media_item_id": item.id,
                    "target": "sda",
                    "bus": "sata",
                    "expected_source": "",
                },
            },
        )
        assert 200 == preview.status_code
        payload = preview.json()
        assert "cdrom_platform_mount" == payload["change_type"]
        assert "+<source protocol='http'>" == payload["diff_text"]
        client.app.state.task_coordinator.stop()
        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/apply",
            headers=headers,
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
                "change_type": "cdrom_platform_mount",
            },
        )
        assert 201 == response.status_code
        assert response.json()["location"].startswith("/tasks/")
