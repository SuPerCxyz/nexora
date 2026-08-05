import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select
from web.test_vms import DOMAIN_UUID, _initialize, _seed_vm

from nexora.app import create_app
from nexora.media.store import MediaObservation
from nexora.resources.models import ResourceIndex
from nexora.tasks.read_service import TaskReadService
from nexora.web.security import CSRF_COOKIE


class CachedIsoStub:
    def preview_cached_mount(
        self,
        _vm_base: object,
        media_item_id: str,
        *,
        target: str,
        bus: str,
        expected_source: str | None,
    ) -> object:
        assert media_item_id
        assert ("sda", "sata", None) == (target, bus, expected_source)
        plan = SimpleNamespace(
            id="cache-plan", change_type="cdrom_cache_mount", diff_text="+/var/tmp/nexora-media"
        )
        return SimpleNamespace(plan=plan, confirmation_token="cache-confirmation")

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
        change_type: str,
    ) -> object:
        assert ("cache-plan", "cache-confirmation") == (plan_id, token)
        assert "cdrom_cache_mount" == change_type
        return SimpleNamespace(id=plan_id, change_type=change_type)


def test_cached_iso_preview_enqueues_eight_step_task(settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        item = _add_cdrom_and_media(client)
        client.app.state.vm_cached_iso_service = CachedIsoStub()
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        preview = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/preview",
            headers=headers,
            json={
                "operation": "cached_iso_mount",
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
        assert "cdrom_cache_mount" == payload["change_type"]
        client.app.state.task_coordinator.stop()
        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/apply",
            headers=headers,
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
                "change_type": "cdrom_cache_mount",
            },
        )
        assert 201 == response.status_code
        task_id = response.json()["task_id"]
        task = TaskReadService(client.app.state.database).detail(task_id)
        assert task is not None and 8 == task.task.total_steps


def _add_cdrom_and_media(client: TestClient) -> object:
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
    with client.app.state.database.session() as session:
        resource = session.scalar(
            select(ResourceIndex).where(ResourceIndex.resource_type == "virtual_machine")
        )
        assert resource is not None
        details = json.loads(resource.details_json)
        details["disks"] = [
            {
                "type": "file",
                "device": "cdrom",
                "target": "sda",
                "bus": "sata",
                "source": None,
            }
        ]
        resource.details_json = json.dumps(details)
    return item
