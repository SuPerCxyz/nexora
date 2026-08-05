"""Integration test for Ubuntu 26.04 LTS KVM node with non-root sudo user."""

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from nexora.app import create_app
from nexora.config import Settings
from nexora.hosts.models import Host
from nexora.hosts.removal_models import HostRemovalMode
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.models import Task, TaskStatus
from nexora.web.security import CSRF_COOKIE, PREAUTH_CSRF_COOKIE

HOST = os.getenv("NEXORA_UBUNTU_HOST")
KEY_FILE = os.getenv("NEXORA_UBUNTU_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="Ubuntu 26.04 LTS KVM node is not configured",
)


def test_ubuntu_node_onboard_discover_and_remove(settings: Settings) -> None:
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        _resource(client, host_id, ResourceType.STORAGE_POOL, "nexora-it-dir")
        _resource(client, host_id, ResourceType.VIRTUAL_MACHINE, "nexora-it-existing")

        removal = client.app.state.host_removal_service
        preview = removal.preview(host_id, HostRemovalMode.CLEAN_TEMPORARY)
        assert preview is not None
        plan = removal.confirm(
            preview.plan.id,
            preview.confirmation_token,
            "ubuntu-2604-it",
            host_id,
        )
        task = client.app.state.task_queue.enqueue(
            TaskCreate(
                task_type="host.remove",
                title="Remove Ubuntu integration host",
                idempotency_scope=f"host:{host_id}:ubuntu-removal",
                idempotency_key=plan.id,
                host_id=host_id,
                resource_type="host",
                resource_id=plan.id,
                total_steps=3,
            )
        )
        _wait_task(client, task)
        with client.app.state.database.session() as session:
            assert session.get(Host, host_id) is None


def _initialize(client: TestClient) -> None:
    client.get("/initialize")
    token = client.cookies.get(PREAUTH_CSRF_COOKIE)
    assert token
    response = client.post(
        "/initialize",
        data={
            "csrf_token": token,
            "username": "admin",
            "password": "integration-password",
            "confirmation": "integration-password",
        },
    )
    assert 200 == response.status_code
    client.post(
        "/login",
        data={
            "csrf_token": client.cookies.get(PREAUTH_CSRF_COOKIE),
            "username": "admin",
            "password": "integration-password",
        },
        follow_redirects=False,
    )


def _onboard(client: TestClient, private_key: str) -> str:
    response = client.post(
        "/hosts",
        data={
            "csrf_token": client.cookies.get(CSRF_COOKIE),
            "name": "ubuntu-2604-it",
            "address": HOST,
            "ssh_port": "22",
            "ssh_username": "ubuntu",
            "authentication_method": "private_key",
            "password": "",
            "private_key": private_key,
            "private_key_passphrase": "",
            "sudo_mode": "passwordless",
            "labels": "integration",
            "notes": "Ubuntu 26.04 LTS integration node",
        },
        follow_redirects=False,
    )
    assert 303 == response.status_code, response.text
    host_id = response.headers["location"].split("/")[2]
    with client.app.state.database.session() as session:
        host = session.get(Host, host_id)
        assert host is not None
        digest = host.pending_host_key_digest
    assert digest
    confirmed = client.post(
        f"/hosts/{host_id}/confirm",
        data={
            "csrf_token": client.cookies.get(CSRF_COOKIE),
            "host_key_digest": digest,
        },
        follow_redirects=False,
    )
    assert 303 == confirmed.status_code, confirmed.text
    return host_id


def _wait_for_task_types(
    client: TestClient,
    host_id: str,
    expected: set[str],
) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        with client.app.state.database.session() as session:
            tasks = list(session.scalars(select(Task).where(Task.host_id == host_id)))
        observed = {task.task_type for task in tasks}
        failed = [task for task in tasks if task.status == TaskStatus.FAILED]
        assert not failed, [(task.task_type, task.message) for task in failed]
        if expected <= observed and all(
            task.status == TaskStatus.SUCCEEDED for task in tasks if task.task_type in expected
        ):
            return
        time.sleep(0.1)
    raise AssertionError("remote host tasks did not finish")


def _wait_task(client: TestClient, task: Task) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        with client.app.state.database.session() as session:
            current = session.get(Task, task.id)
        assert current is not None
        if current.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED):
            assert current.status == TaskStatus.SUCCEEDED, current.message
            return
        time.sleep(0.1)
    raise AssertionError("task did not finish")


def _resource(
    client: TestClient,
    host_id: str,
    resource_type: ResourceType,
    name: str,
) -> ResourceIndex:
    with client.app.state.database.session() as session:
        resource = session.scalar(
            select(ResourceIndex).where(
                ResourceIndex.host_id == host_id,
                ResourceIndex.resource_type == resource_type,
                ResourceIndex.display_name == name,
            )
        )
        assert resource is not None
        session.expunge(resource)
        return resource
