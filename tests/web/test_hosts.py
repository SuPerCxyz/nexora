import time
from base64 import b64encode
from datetime import UTC, datetime
from threading import Event

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from nexora.app import create_app
from nexora.config import Settings
from nexora.hosts.models import (
    AuthenticationMethod,
    Host,
    HostStatus,
    SudoMode,
)
from nexora.hosts.removal_models import HostRemovalTombstone
from nexora.remote.host_keys import HostKeyCandidate
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnectionProfile
from nexora.resources.models import ResourceScan
from nexora.tasks.models import Task, TaskStatus
from nexora.web.security import CSRF_COOKIE, PREAUTH_CSRF_COOKIE


class SuccessBackend:
    def run(
        self,
        _profile: SSHConnectionProfile,
        remote_command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult:
        del timeout, stdin, cancel_event
        if "id -u" in remote_command:
            stdout = b"0\n"
        elif remote_command.endswith("lscpu -J"):
            stdout = (
                b'{"lscpu":[{"field":"Architecture:","data":"x86_64"},'
                b'{"field":"CPU(s):","data":"4"}]}'
            )
        elif "command -v" in remote_command:
            stdout = b"/usr/bin/tool\n"
        elif (
            remote_command.endswith("list --all --uuid")
            or "pool-list --all --name" in remote_command
            or "nodedev-list" in remote_command
        ):
            stdout = b""
        elif (
            " ip -j " in remote_command
            or " ip -d -j " in remote_command
            or " bridge -j " in remote_command
        ):
            stdout = b"[]"
        else:
            stdout = b"ok\n"
        return ProcessResult(0, stdout, b"", False, False, False, False, 0.01)


def _initialize(client: TestClient) -> None:
    client.get("/initialize")
    token = client.cookies.get(PREAUTH_CSRF_COOKIE)
    assert token
    response = client.post(
        "/initialize",
        data={
            "csrf_token": token,
            "username": "admin",
            "password": "a-valid-password",
            "confirmation": "a-valid-password",
        },
    )
    assert 200 == response.status_code


def _candidate() -> HostKeyCandidate:
    return HostKeyCandidate(
        "kvm.example.test",
        22,
        "ssh-ed25519",
        b64encode(b"host-key").decode(),
    )


def _submit_host(client: TestClient) -> str:
    csrf = client.cookies.get(CSRF_COOKIE)
    response = client.post(
        "/internal/hosts/onboarding",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "node-one",
            "address": "kvm.example.test",
            "ssh_port": 22,
            "ssh_username": "root",
            "authentication_method": "password",
            "password": "ssh-password",
            "private_key": None,
            "private_key_passphrase": None,
            "sudo_mode": "none",
            "labels": ["lab"],
            "notes": "",
        },
    )
    assert 201 == response.status_code
    return response.json()["host_id"]


def test_host_form_scans_then_requires_explicit_fingerprint_confirmation(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        client.app.state.host_onboarding_service.scanner = lambda _host, _port: [_candidate()]

        host_id = _submit_host(client)
        confirmation = client.get(f"/hosts/{host_id}/confirm")
        confirmation_api = client.get(f"/internal/hosts/{host_id}/host-key-confirmation")

        assert 200 == confirmation.status_code
        assert 'id="nexora-root"' in confirmation.text
        assert "SHA256:" in confirmation_api.text
        assert "kvm.example.test:22" in confirmation_api.text
        assert "ssh-password" not in confirmation_api.text


def test_internal_host_onboarding_scans_then_confirms_without_echoing_secret(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        client.app.state.host_onboarding_service.scanner = lambda _host, _port: [_candidate()]
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        started = client.post(
            "/internal/hosts/onboarding",
            headers=headers,
            json={
                "name": "react-node",
                "address": "kvm.example.test",
                "ssh_port": 22,
                "ssh_username": "root",
                "authentication_method": "password",
                "password": "ssh-password",
                "sudo_mode": "none",
                "labels": ["lab"],
            },
        )

        assert 201 == started.status_code
        assert "ssh-password" not in started.text
        host_id = started.json()["host_id"]
        confirmation = client.get(f"/internal/hosts/{host_id}/host-key-confirmation")
        assert 200 == confirmation.status_code
        assert "SHA256:" in confirmation.text
        assert "ssh-password" not in confirmation.text

        client.app.state.task_coordinator.stop()
        confirmed = client.post(
            f"/internal/hosts/{host_id}/host-key-confirmation",
            headers=headers,
            json={"host_key_digest": confirmation.json()["host_key_digest"]},
        )
        assert 201 == confirmed.status_code
        assert f"/hosts/{host_id}" == confirmed.json()["location"]


def test_confirmed_host_enqueues_and_completes_read_only_probe(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        client.app.state.host_onboarding_service.scanner = lambda _host, _port: [_candidate()]
        client.app.state.remote_executor.backend = SuccessBackend()
        host_id = _submit_host(client)
        with client.app.state.database.session() as session:
            host = session.get(Host, host_id)
            assert host is not None
            digest = host.pending_host_key_digest
            assert digest

        response = client.post(
            f"/internal/hosts/{host_id}/host-key-confirmation",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={"host_key_digest": digest},
        )

        assert 201 == response.status_code
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with client.app.state.database.session() as session:
                tasks = list(session.scalars(select(Task).where(Task.host_id == host_id)))
                if len(tasks) == 2 and all(task.status == TaskStatus.SUCCEEDED for task in tasks):
                    break
            time.sleep(0.01)
        else:
            with client.app.state.database.session() as session:
                tasks = list(session.scalars(select(Task).where(Task.host_id == host_id)))
                states = [(task.task_type, task.status, task.message) for task in tasks]
            raise AssertionError(f"host probe and discovery tasks did not complete: {states}")
        with client.app.state.database.session() as session:
            capability_task = next(
                task for task in tasks if task.task_type == "host.capability_probe"
            )
            assert 22 == capability_task.total_steps
            scan_count = session.scalar(select(func.count()).select_from(ResourceScan))
            assert 8 == scan_count

        rescan = client.post(
            f"/internal/hosts/{host_id}/scan",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
        )
        assert 201 == rescan.status_code
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with client.app.state.database.session() as session:
                tasks = list(session.scalars(select(Task).where(Task.host_id == host_id)))
                if len(tasks) == 4 and all(task.status == TaskStatus.SUCCEEDED for task in tasks):
                    break
            time.sleep(0.01)
        else:
            raise AssertionError("manual host refresh did not complete")
        with client.app.state.database.session() as session:
            tasks = list(session.scalars(select(Task).where(Task.host_id == host_id)))
            assert 2 == sum(task.task_type == "host.capability_probe" for task in tasks)
            assert 2 == sum(task.task_type == "host.resource_discovery" for task in tasks)


def test_local_only_removal_requires_preview_name_and_persists_tombstone(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        now = datetime.now(UTC)
        with client.app.state.database.session() as session:
            session.add(
                Host(
                    id="host-remove",
                    name="remove-me",
                    address="remove.example.test",
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

        host_list = client.get("/hosts")
        page = client.get("/hosts/host-remove")
        preview = client.post(
            "/internal/hosts/host-remove/removal/preview",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={"mode": "local_only"},
        )
        assert 200 == host_list.status_code
        assert 'id="nexora-root"' in host_list.text
        host_api = client.get("/internal/hosts")
        assert "ready" == host_api.json()["items"][0]["status"]
        assert 200 == page.status_code
        assert 200 == preview.status_code
        plan_id = preview.json()["plan_id"]
        token = preview.json()["confirmation_token"]

        confirmed = client.post(
            "/internal/hosts/host-remove/removal/apply",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={
                "plan_id": plan_id,
                "confirmation_token": token,
                "confirmation_name": "remove-me",
            },
        )

        assert 201 == confirmed.status_code
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with client.app.state.database.session() as session:
                host = session.get(Host, "host-remove")
                tombstone = session.scalar(select(HostRemovalTombstone))
                if host is None and tombstone is not None:
                    break
            time.sleep(0.01)
        else:
            raise AssertionError("host removal task did not complete")
