import json
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from web.test_storage import _seed_host
from web.test_vms import _initialize

from nexora.app import create_app
from nexora.config import Settings
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.models import Task
from nexora.web.security import CSRF_COOKIE


class NetworkWriteStub:
    def __init__(self) -> None:
        self.plans = self

    def preview_bridge_create(self, host_id: str, change: object) -> object:
        assert "host-1" == host_id
        plan = SimpleNamespace(
            id="network-plan",
            change_type="bridge_create",
            target_iface="br1",
            rollback_script="ip link delete br1",
        )
        return SimpleNamespace(plan=plan, confirmation_token="network-confirmation")

    def confirm(self, plan_id: str, token: str, *, host_id: str) -> object:
        assert ("network-plan", "network-confirmation", "host-1") == (
            plan_id,
            token,
            host_id,
        )
        return SimpleNamespace(
            id=plan_id,
            change_type="bridge_create",
            target_iface="br1",
        )


def test_network_topology_page_reads_cached_resources_without_task(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        _seed_interface(client)
        with client.app.state.database.session() as session:
            before = len(list(session.query(Task)))

        response = client.get("/networks?host_id=host-1")
        api = client.get("/internal/networks?host_id=host-1")

        assert 200 == response.status_code
        assert 'id="nexora-root"' in response.text
        assert "host-1" == api.json()["selected_host_id"]
        node = api.json()["topology"]["nodes"][0]
        assert "eth0" == node["label"]
        assert node["default_route"]
        with client.app.state.database.session() as session:
            assert before == len(list(session.query(Task)))


def test_network_topology_page_rejects_unknown_host(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        response = client.get("/internal/networks?host_id=missing")
        assert 404 == response.status_code


def test_internal_network_preview_and_apply_use_csrf(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        client.app.state.network_write_service = NetworkWriteStub()
        denied = client.post(
            "/internal/networks/bridge/preview",
            json={"host_id": "host-1", "bridge_name": "br1"},
        )
        preview = client.post(
            "/internal/networks/bridge/preview",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={"host_id": "host-1", "bridge_name": "br1"},
        )
        client.app.state.task_coordinator.stop()
        applied = client.post(
            "/internal/networks/apply",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={
                "host_id": "host-1",
                "plan_id": preview.json()["plan_id"],
                "confirmation_token": preview.json()["confirmation_token"],
            },
        )

        assert 403 == denied.status_code
        assert "ip link delete br1" == preview.json()["rollback_script"]
        assert 201 == applied.status_code
        assert applied.json()["location"].startswith("/tasks/")


def _seed_interface(client: TestClient) -> None:
    now = datetime.now(UTC)
    with client.app.state.database.session() as session:
        session.add(
            ResourceIndex(
                id="interface-1",
                host_id="host-1",
                resource_type=ResourceType.HOST_INTERFACE,
                native_id="2",
                display_name="eth0",
                status=ResourceStatus.READ_ONLY,
                source="existing",
                live_hash="a" * 64,
                hash_algorithm="sha256-json-v1",
                observed_generation=1,
                details_json=json.dumps(
                    {
                        "ifindex": 2,
                        "kind": "physical",
                        "mtu": 1500,
                        "operstate": "UP",
                        "flags": ["LOWER_UP"],
                        "addresses": [{"local": "192.0.2.10"}],
                        "routes": [{"dst": "default", "gateway": "192.0.2.1"}],
                    }
                ),
                labels_json="[]",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
