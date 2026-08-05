"""Real alternate-distribution onboarding and inventory test."""

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from nexora.app import create_app
from nexora.config import Settings
from nexora.hosts.models import Host, HostCapability
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.tasks.models import Task, TaskStatus
from nexora.web.security import CSRF_COOKIE, PREAUTH_CSRF_COOKIE

HOST = os.getenv("NEXORA_DISTRIBUTION_HOST")
PORT = os.getenv("NEXORA_DISTRIBUTION_PORT", "22")
USER = os.getenv("NEXORA_DISTRIBUTION_USER", "nexora")
KEY_FILE = os.getenv("NEXORA_DISTRIBUTION_PRIVATE_KEY_FILE")
EXPECTED_OS = os.getenv("NEXORA_DISTRIBUTION_EXPECTED_OS", "Debian GNU/Linux 13")
EXPECTED_VM = os.getenv("NEXORA_DISTRIBUTION_EXPECTED_VM", "nexora-it-debian-existing")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="alternate distribution integration environment is not configured",
)


def test_real_distribution_onboarding_and_inventory(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        client.get("/initialize")
        response = client.post(
            "/initialize",
            data={
                "csrf_token": client.cookies.get(PREAUTH_CSRF_COOKIE),
                "username": "admin",
                "password": "integration-password",
                "confirmation": "integration-password",
            },
        )
        assert 200 == response.status_code
        response = client.post(
            "/hosts",
            data={
                "csrf_token": client.cookies.get(CSRF_COOKIE),
                "name": "nexora-it-distribution",
                "address": HOST,
                "ssh_port": PORT,
                "ssh_username": USER,
                "authentication_method": "private_key",
                "password": "",
                "private_key": Path(KEY_FILE or "").read_text(),
                "private_key_passphrase": "",
                "sudo_mode": "passwordless",
                "labels": "integration",
                "notes": "Nested alternate-distribution node",
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
        response = client.post(
            f"/hosts/{host_id}/confirm",
            data={
                "csrf_token": client.cookies.get(CSRF_COOKIE),
                "host_key_digest": digest,
            },
            follow_redirects=False,
        )
        assert 303 == response.status_code, response.text
        _wait(client, host_id)
        with client.app.state.database.session() as session:
            capabilities = list(
                session.scalars(select(HostCapability).where(HostCapability.host_id == host_id))
            )
            resources = list(
                session.scalars(select(ResourceIndex).where(ResourceIndex.host_id == host_id))
            )
        assert any(EXPECTED_OS in (item.value_json or "") for item in capabilities)
        assert any(
            item.resource_type == ResourceType.VIRTUAL_MACHINE and item.display_name == EXPECTED_VM
            for item in resources
        )
        assert any(item.resource_type == ResourceType.HOST_INTERFACE for item in resources)


def _wait(client: TestClient, host_id: str) -> None:
    deadline = time.monotonic() + 120
    expected = {"host.capability_probe", "host.resource_discovery"}
    while time.monotonic() < deadline:
        with client.app.state.database.session() as session:
            tasks = list(session.scalars(select(Task).where(Task.host_id == host_id)))
        assert not [task for task in tasks if task.status == TaskStatus.FAILED]
        if expected <= {task.task_type for task in tasks} and all(
            task.status == TaskStatus.SUCCEEDED for task in tasks
        ):
            return
        time.sleep(0.1)
    raise AssertionError("alternate distribution tasks did not finish")
