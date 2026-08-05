from types import SimpleNamespace

from fastapi.testclient import TestClient
from web.test_vms import DOMAIN_UUID, _initialize, _seed_vm

from nexora.app import create_app
from nexora.config import Settings


class GuestAgentService:
    def read(self, host_id: str, vm_uuid: str) -> object:
        assert ("host-1", DOMAIN_UUID) == (host_id, vm_uuid)
        return SimpleNamespace(
            state="connected",
            channel_configured=True,
            hostname="guest.example.test",
            addresses=(
                SimpleNamespace(
                    interface="eth0",
                    address="192.0.2.10",
                    prefix=24,
                    family="ipv4",
                    mac="52:54:00:12:34:56",
                ),
            ),
            message=None,
        )


def test_vm_guest_agent_returns_authenticated_json(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        client.app.state.vm_guest_agent_service = GuestAgentService()

        response = client.get(f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/guest-agent")

        assert 200 == response.status_code
        payload = response.json()
        assert "connected" == payload["state"]
        assert "guest.example.test" == payload["hostname"]
        assert "192.0.2.10" == payload["addresses"][0]["address"]
        assert 24 == payload["addresses"][0]["prefix"]


def test_vm_guest_agent_requires_authentication(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/guest-agent",
            follow_redirects=False,
        )

        assert 401 == response.status_code
        assert "authentication_required" == response.json()["code"]
