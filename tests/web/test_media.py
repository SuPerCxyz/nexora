import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from nexora.app import create_app
from nexora.config import Settings
from nexora.hosts.models import (
    AuthenticationMethod,
    Host,
    HostStatus,
    SudoMode,
)
from nexora.media.credentials import MediaCredentialError
from nexora.media.models import MediaCredential, MediaItem
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.models import Task, TaskStatus
from nexora.web.security import CSRF_COOKIE, PREAUTH_CSRF_COOKIE


def test_media_page_runs_persistent_scan_without_exposing_absolute_path(
    settings: Settings,
) -> None:
    settings.library_dir.mkdir(parents=True)
    media = settings.library_dir / "iso" / "linux" / "debian-amd64.iso"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"small-test-iso")

    with TestClient(create_app(settings)) as client:
        _initialize(client)
        empty = client.get("/media")
        empty_api = client.get("/internal/media")
        assert 200 == empty.status_code
        assert 'id="nexora-root"' in empty.text
        assert [] == empty_api.json()["items"]
        response = client.post(
            "/internal/media/scan",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
        )
        assert 201 == response.status_code
        task_id = response.json()["task_id"]
        _wait_for_success(client, task_id)

        listing = client.get("/media")
        listing_api = client.get("/internal/media")
        assert 200 == listing.status_code
        assert "debian-amd64.iso" == listing_api.json()["items"][0]["file_name"]
        assert "iso/linux/debian-amd64.iso" == listing_api.json()["items"][0]["relative_path"]
        assert str(settings.library_dir) not in listing_api.text

        item = client.app.state.media_index_store.list_items()[0]
        internal_issued = client.post(
            f"/internal/media/{item.id}/credentials",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
        )
        assert 201 == internal_issued.status_code
        assert internal_issued.json()["token"] not in internal_issued.json()["content_url"]
        revoked = client.post(
            f"/internal/media/credentials/{internal_issued.json()['credential_id']}/revoke",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
        )
        assert {"revoked": True} == revoked.json()
        issued = client.app.state.media_credential_service.issue(item.id)
        content_url = f"/media/content/{issued.credential.id}"
        authorization = {"Authorization": f"Bearer {issued.token}"}
        with client.app.state.database.session() as session:
            stored = session.get(MediaCredential, issued.credential.id)
            assert stored is not None
            assert issued.token != stored.token_digest

        assert 401 == client.get(content_url).status_code
        head = client.head(content_url, headers=authorization)
        assert 200 == head.status_code
        assert str(len(b"small-test-iso")) == head.headers["content-length"]
        assert b"" == head.content
        partial = client.get(
            content_url,
            headers={**authorization, "Range": "bytes=2-6"},
        )
        assert 206 == partial.status_code
        assert b"all-t" == partial.content
        assert f"bytes 2-6/{len(b'small-test-iso')}" == partial.headers["content-range"]
        if_range_miss = client.get(
            content_url,
            headers={
                **authorization,
                "Range": "bytes=2-6",
                "If-Range": '"different"',
            },
        )
        assert 200 == if_range_miss.status_code
        assert b"small-test-iso" == if_range_miss.content
        invalid = client.get(
            content_url,
            headers={**authorization, "Range": "bytes=0-1,3-4"},
        )
        assert 416 == invalid.status_code
        assert client.app.state.media_credential_service.revoke(issued.credential.id)
        assert 401 == client.get(content_url, headers=authorization).status_code

        now = datetime.now(UTC)
        with client.app.state.database.session() as session:
            session.add(
                Host(
                    id="host-media",
                    name="media-node",
                    address="192.0.2.10",
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
        node_credential = client.app.state.media_credential_service.issue_for_node(
            item.id,
            host_id="host-media",
            vm_uuid="11111111-1111-1111-1111-111111111111",
        )
        authenticated = client.app.state.media_credential_service.authenticate_node(
            node_credential.id,
            "192.0.2.10",
        )
        assert item.id == authenticated.id
        with pytest.raises(MediaCredentialError):
            client.app.state.media_credential_service.authenticate_node(
                node_credential.id,
                "192.0.2.11",
            )


def test_internal_media_copy_uses_indexed_pool_version(settings: Settings) -> None:
    media_id = "11111111-1111-1111-1111-111111111111"
    now = datetime.now(UTC)
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        with client.app.state.database.session() as session:
            session.add(
                Host(
                    id="copy-host",
                    name="copy-node",
                    address="192.0.2.20",
                    ssh_port=22,
                    ssh_username="root",
                    authentication_method="private_key",
                    sudo_mode="none",
                    libvirt_uri="qemu:///system",
                    status="ready",
                    labels_json="[]",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                ResourceIndex(
                    id="copy-pool",
                    host_id="copy-host",
                    resource_type=ResourceType.STORAGE_POOL,
                    native_id="pool-native",
                    display_name="images",
                    status=ResourceStatus.MANAGED,
                    source="existing",
                    persistent_hash="a" * 64,
                    hash_algorithm="sha256-json-v1",
                    observed_generation=2,
                    details_json='{"pool_type":"dir","active":true,"target_path":"/images"}',
                    labels_json="[]",
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            session.add(
                MediaItem(
                    id=media_id,
                    relative_path="images/base.qcow2",
                    file_name="base.qcow2",
                    kind="qcow2",
                    status="available",
                    size_bytes=1024,
                    modified_ns=1,
                    file_device=1,
                    file_inode=1,
                    sha256="b" * 64,
                    image_format="qcow2",
                    backing_chain_json="[]",
                    observed_generation=1,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )

        page = client.get(f"/media/{media_id}/copy")
        options = client.get(f"/internal/media/{media_id}/copy")
        client.app.state.task_coordinator.stop()
        copied = client.post(
            f"/internal/media/{media_id}/copy",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={"pool_resource_id": "copy-pool", "target_file_name": "copied.qcow2"},
        )

        assert 'id="nexora-root"' in page.text
        assert "copy-pool" == options.json()["targets"][0]["pool_resource_id"]
        assert 201 == copied.status_code
        with client.app.state.database.session() as session:
            task = session.get(Task, copied.json()["task_id"])
            assert task is not None
            assert '"pool_generation":2' in (task.input_summary or "")


def _initialize(client: TestClient) -> None:
    client.get("/initialize")
    response = client.post(
        "/initialize",
        data={
            "csrf_token": client.cookies.get(PREAUTH_CSRF_COOKIE),
            "username": "admin",
            "password": "a-valid-password",
            "confirmation": "a-valid-password",
        },
    )
    assert 200 == response.status_code


def _wait_for_success(client: TestClient, task_id: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with client.app.state.database.session() as session:
            task = session.get(Task, task_id)
            if task is not None and task.status == TaskStatus.SUCCEEDED:
                return
            if task is not None and task.status == TaskStatus.FAILED:
                raise AssertionError(task.error_message)
        time.sleep(0.01)
    raise AssertionError("media scan task did not complete")
