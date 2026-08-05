import json
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect
from web.test_vms import DOMAIN_UUID, _initialize, _seed_vm

from nexora.app import create_app
from nexora.config import Settings
from nexora.consoles.models import ConsoleSession, ConsoleStatus
from nexora.resources.models import ResourceDocument, ResourceIndex
from nexora.web.security import CSRF_COOKIE

SERIAL = (
    b"<serial type='pty'><target port='0'/></serial>"
    b"<console type='pty'><target type='serial' port='0'/></console>"
)


class Connection:
    def __init__(self) -> None:
        self.reads = [b"serial-ready\r\n", b""]
        self.writes: list[bytes] = []

    async def read(self) -> bytes:
        return self.reads.pop(0)

    def write(self, data: bytes) -> None:
        self.writes.append(data)


class Connector:
    def __init__(self) -> None:
        self.connection = Connection()

    @asynccontextmanager
    async def open(self, host_id: str, vm_uuid: str):  # type: ignore[no-untyped-def]
        assert ("host-1", DOMAIN_UUID) == (host_id, vm_uuid)
        yield self.connection


def test_serial_console_uses_one_time_bound_websocket_token(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_active_serial(client)
        connector = Connector()
        client.app.state.serial_console_connector = connector

        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/console",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={"kind": "serial"},
        )

        assert 201 == response.status_code
        session_id = response.json()["session_id"]
        token = response.json()["token"]
        assert token not in str(response.url)
        assert token not in session_id
        with client.app.state.database.session() as session:
            stored = session.get(ConsoleSession, session_id)
            assert stored is not None
            assert token != stored.token_digest

        with client.websocket_connect(
            f"/ws/consoles/{session_id}",
            subprotocols=["nexora.console", f"nexora.token.{token}"],
            headers={"origin": "http://testserver"},
        ) as websocket:
            assert "nexora.console" == websocket.accepted_subprotocol
            assert b"serial-ready\r\n" == websocket.receive_bytes()

        with client.app.state.database.session() as session:
            stored = session.get(ConsoleSession, session_id)
            assert stored is not None
            assert ConsoleStatus.CLOSED == stored.status
        try:
            with client.websocket_connect(
                f"/ws/consoles/{session_id}",
                subprotocols=["nexora.console", f"nexora.token.{token}"],
                headers={"origin": "http://testserver"},
            ):
                raise AssertionError("replayed token was accepted")
        except WebSocketDisconnect as exc:
            assert 4403 == exc.code


def test_serial_console_rejects_cross_origin_without_consuming_token(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_active_serial(client)
        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/console",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={"kind": "serial"},
        )
        session_id = response.json()["session_id"]
        token = response.json()["token"]
        try:
            with client.websocket_connect(
                f"/ws/consoles/{session_id}",
                subprotocols=["nexora.console", f"nexora.token.{token}"],
                headers={"origin": "https://attacker.example"},
            ):
                raise AssertionError("cross-origin console was accepted")
        except WebSocketDisconnect as exc:
            assert 4403 == exc.code
        with client.app.state.database.session() as session:
            stored = session.get(ConsoleSession, session_id)
            assert stored is not None
            assert ConsoleStatus.PENDING == stored.status


def test_serial_console_rejects_csrf_and_stopped_vm(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        path = f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/console"
        assert 403 == client.post(path, json={"kind": "serial"}).status_code
        response = client.post(
            path,
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={"kind": "serial"},
        )
        assert 409 == response.status_code


def _seed_active_serial(client: TestClient) -> None:
    _seed_vm(client)
    with client.app.state.database.session() as session:
        resource = session.scalar(select(ResourceIndex))
        document = session.scalar(select(ResourceDocument))
        assert resource is not None
        assert document is not None
        details = json.loads(resource.details_json)
        details.update({"active": True, "state": "running"})
        resource.details_json = json.dumps(details)
        document.content = document.content.replace(
            b"<devices/>", b"<devices>" + SERIAL + b"</devices>"
        )
