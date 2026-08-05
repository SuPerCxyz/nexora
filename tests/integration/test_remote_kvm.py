import os
import time
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from nexora.app import create_app
from nexora.config import Settings
from nexora.hosts.models import Host
from nexora.hosts.removal_models import HostRemovalMode
from nexora.media.models import MediaItem
from nexora.media.store import MediaObservation
from nexora.remote.commands import CommandSpec
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.tasks.definitions import TaskCreate
from nexora.tasks.models import Task, TaskStatus
from nexora.web.security import CSRF_COOKIE, PREAUTH_CSRF_COOKIE

HOST = os.getenv("NEXORA_INTEGRATION_HOST")
KEY_FILE = os.getenv("NEXORA_INTEGRATION_PRIVATE_KEY_FILE")
pytestmark = pytest.mark.skipif(
    not HOST or not KEY_FILE,
    reason="dedicated remote KVM integration environment is not configured",
)


def test_real_host_discovery_image_copy_and_zero_residue(settings: Settings) -> None:
    source = _create_media(settings.library_dir)
    private_key = Path(KEY_FILE or "").read_text()
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host_id = _onboard(client, private_key)
        _wait_for_task_types(
            client,
            host_id,
            {"host.capability_probe", "host.resource_discovery"},
        )
        pool = _resource(client, host_id, ResourceType.STORAGE_POOL, "nexora-it-dir")
        _resource(client, host_id, ResourceType.VIRTUAL_MACHINE, "nexora-it-existing")

        _remote_cleanup(client, host_id, pool, "nexora-it-copied.raw")
        item = _index_media(client, settings.library_dir)
        copy_task = _copy_media(client, item, pool)
        _wait_task(client, copy_task)
        copied_path = _target_path(pool) + "/nexora-it-copied.raw"
        result = client.app.state.remote_executor.run(
            host_id,
            CommandSpec("sha256sum", ("--", copied_path)),
            sudo=False,
            timeout=30,
        )
        assert 0 == result.exit_code
        assert item.sha256 == result.stdout.decode().split()[0]
        assert len(source) == item.size_bytes

        removal = client.app.state.host_removal_service
        preview = removal.preview(host_id, HostRemovalMode.CLEAN_TEMPORARY)
        plan = removal.confirm(
            preview.plan.id,
            preview.confirmation_token,
            "nexora-it-node",
            host_id,
        )
        task = client.app.state.task_queue.enqueue(
            TaskCreate(
                task_type="host.remove",
                title="Remove integration host",
                idempotency_scope=f"host:{host_id}:integration-removal",
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


def _onboard(client: TestClient, private_key: str) -> str:
    response = client.post(
        "/hosts",
        data={
            "csrf_token": client.cookies.get(CSRF_COOKIE),
            "name": "nexora-it-node",
            "address": HOST,
            "ssh_port": "22",
            "ssh_username": "root",
            "authentication_method": "private_key",
            "password": "",
            "private_key": private_key,
            "private_key_passphrase": "",
            "sudo_mode": "none",
            "labels": "integration",
            "notes": "Dedicated nested KVM integration node",
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


def _create_media(library_dir: Path) -> bytes:
    source = b"nexora-integration-image" * 50_000
    path = library_dir / "images" / "nexora-it-source.raw"
    path.parent.mkdir(parents=True)
    path.write_bytes(source)
    return source


def _index_media(client: TestClient, library_dir: Path) -> MediaItem:
    path = library_dir / "images" / "nexora-it-source.raw"
    metadata = path.stat()
    content = path.read_bytes()
    store = client.app.state.media_index_store
    scan = store.begin()
    store.complete(
        scan.id,
        [
            MediaObservation(
                relative_path="images/nexora-it-source.raw",
                file_name="nexora-it-source.raw",
                kind="raw",
                size_bytes=metadata.st_size,
                modified_ns=metadata.st_mtime_ns,
                file_device=metadata.st_dev,
                file_inode=metadata.st_ino,
                sha256=sha256(content).hexdigest(),
                image_format="raw",
                virtual_size_bytes=metadata.st_size,
                backing_chain=(),
                classification=None,
                architecture=None,
            )
        ],
    )
    item = store.list_items()[0]
    assert "nexora-it-source.raw" == item.file_name
    return item


def _copy_media(client: TestClient, item: MediaItem, pool: ResourceIndex) -> Task:
    response = client.post(
        f"/media/{item.id}/copy",
        data={
            "csrf_token": client.cookies.get(CSRF_COOKIE),
            "pool_resource_id": pool.id,
            "target_file_name": "nexora-it-copied.raw",
        },
        follow_redirects=False,
    )
    assert 303 == response.status_code, response.text
    task_id = response.headers["location"].split("/")[2]
    with client.app.state.database.session() as session:
        task = session.get(Task, task_id)
        assert task is not None
        session.expunge(task)
        return task


def _wait_task(client: TestClient, task: Task) -> None:
    _wait_task_id(client, task.id)


def _wait_task_id(client: TestClient, task_id: str) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        with client.app.state.database.session() as session:
            task = session.get(Task, task_id)
            assert task is not None
            status = task.status
        if status == TaskStatus.SUCCEEDED:
            return
        assert status not in {TaskStatus.FAILED, TaskStatus.CANCELLED}
        time.sleep(0.1)
    raise AssertionError(f"task did not finish: {task_id}")


def _target_path(pool: ResourceIndex) -> str:
    import json

    value = json.loads(pool.details_json)["target_path"]
    assert isinstance(value, str)
    return value


def _remote_cleanup(
    client: TestClient,
    host_id: str,
    pool: ResourceIndex,
    file_name: str,
) -> None:
    path = _target_path(pool) + "/" + file_name
    result = client.app.state.remote_executor.run(
        host_id,
        CommandSpec("rm", ("-f", "--", path)),
        sudo=False,
        timeout=30,
    )
    assert 0 == result.exit_code
