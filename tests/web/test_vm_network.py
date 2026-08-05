import json
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from web.test_vms import DOMAIN_UUID, _initialize, _seed_vm

from nexora.app import create_app
from nexora.config import Settings
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.web.security import CSRF_COOKIE


class NetworkServiceStub:
    def preview_attach(
        self,
        vm_base: object,
        *,
        kind: str,
        source: str,
        model: str,
        mac: str | None = None,
        live: bool = False,
    ) -> object:
        assert "bridge" == kind
        assert "br0" == source
        plan = SimpleNamespace(
            id="network-plan", change_type="interface_attach", diff_text="+<interface>"
        )
        return SimpleNamespace(plan=plan, confirmation_token="network-confirmation")

    def preview_detach(
        self,
        vm_base: object,
        *,
        mac: str,
        live: bool = False,
    ) -> object:
        assert "52:54:00:aa:bb:cc" == mac
        plan = SimpleNamespace(
            id="network-plan", change_type="interface_detach", diff_text="-<interface>"
        )
        return SimpleNamespace(plan=plan, confirmation_token="network-confirmation")

    def preview_update(
        self,
        vm_base: object,
        *,
        mac: str,
        kind: str | None = None,
        source: str | None = None,
        model: str | None = None,
        new_mac: str | None = None,
        live: bool = False,
    ) -> object:
        assert "52:54:00:aa:bb:cc" == mac
        assert "br0" == source
        plan = SimpleNamespace(
            id="network-plan", change_type="interface_update", diff_text="~<interface>"
        )
        return SimpleNamespace(plan=plan, confirmation_token="network-confirmation")

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
        change_type: str,
    ) -> object:
        assert ("network-plan", "network-confirmation") == (plan_id, token)
        return SimpleNamespace(id=plan_id, change_type=change_type)


def _seed_network(client: TestClient) -> None:
    now = datetime.now(UTC)
    with client.app.state.database.session() as session:
        session.add(
            ResourceIndex(
                id="net-1",
                host_id="host-1",
                resource_type=ResourceType.LIBVIRT_NETWORK,
                native_id="33333333-3333-3333-3333-333333333333",
                display_name="default",
                status=ResourceStatus.MANAGED,
                source="existing",
                persistent_hash="c" * 64,
                observed_generation=1,
                details_json=json.dumps(
                    {"active": True, "persistent": True, "forward_mode": "nat"}
                ),
                labels_json="[]",
                first_seen_at=now,
                last_seen_at=now,
            )
        )


def test_internal_network_attach_detach_update_previews_and_queues(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        _seed_network(client)
        client.app.state.vm_network_change_service = NetworkServiceStub()
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        attach = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/preview",
            headers=headers,
            json={
                "operation": "interface_attach",
                "values": {"kind": "bridge", "source": "br0", "model": "virtio"},
            },
        )
        assert 200 == attach.status_code
        assert "interface_attach" == attach.json()["change_type"]

        detach = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/preview",
            headers=headers,
            json={
                "operation": "interface_detach",
                "values": {"mac": "52:54:00:aa:bb:cc"},
            },
        )
        assert 200 == detach.status_code
        assert "interface_detach" == detach.json()["change_type"]

        update = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/preview",
            headers=headers,
            json={
                "operation": "interface_update",
                "values": {
                    "mac": "52:54:00:aa:bb:cc",
                    "kind": "bridge",
                    "source": "br0",
                },
            },
        )
        assert 200 == update.status_code
        assert "interface_update" == update.json()["change_type"]

        client.app.state.task_coordinator.stop()
        applied = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/apply",
            headers=headers,
            json={
                "plan_id": attach.json()["plan_id"],
                "confirmation_token": attach.json()["confirmation_token"],
                "change_type": "interface_attach",
            },
        )
        assert 201 == applied.status_code
        assert applied.json()["location"].startswith("/tasks/")


def test_vm_configuration_exposes_interfaces_and_networks(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        _seed_network(client)

        payload = client.get(f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration").json()
        assert "interfaces" in payload
        assert "networks" in payload
        assert any(item["name"] == "default" for item in payload["networks"])
