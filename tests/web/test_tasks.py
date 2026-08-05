from fastapi.testclient import TestClient

from nexora.app import create_app
from nexora.config import Settings
from nexora.tasks.models import TaskStatus
from nexora.tasks.queue import TaskCreate
from nexora.web.security import CSRF_COOKIE, PREAUTH_CSRF_COOKIE


def _initialize(client: TestClient) -> None:
    client.get("/initialize")
    preauth = client.cookies.get(PREAUTH_CSRF_COOKIE)
    assert preauth
    response = client.post(
        "/initialize",
        data={
            "csrf_token": preauth,
            "username": "admin",
            "password": "a-valid-password",
            "confirmation": "a-valid-password",
        },
    )
    assert 200 == response.status_code


def test_task_center_lists_and_opens_persistent_task(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        task = client.app.state.task_queue.enqueue(
            TaskCreate(
                task_type="unregistered",
                title="Scan host",
                idempotency_scope="host:one",
                idempotency_key="scan",
                total_steps=3,
            )
        )

        listing = client.get("/tasks")
        detail = client.get(f"/tasks/{task.id}")
        listing_api = client.get("/internal/tasks")
        detail_api = client.get(f"/internal/tasks/{task.id}")

        assert 200 == listing.status_code
        assert 'id="nexora-root"' in listing.text
        assert 200 == detail.status_code
        assert 'id="nexora-root"' in detail.text
        assert "Scan host" == listing_api.json()["items"][0]["title"]
        assert task.id == detail_api.json()["task"]["id"]


def test_task_cancel_requires_csrf(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        task = client.app.state.task_queue.enqueue(
            TaskCreate(
                task_type="test",
                title="Cancelable",
                idempotency_scope="test",
                idempotency_key="cancel",
            )
        )

        denied = client.post(f"/internal/tasks/{task.id}/cancel")
        allowed = client.post(
            f"/internal/tasks/{task.id}/cancel",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
        )

        assert 403 == denied.status_code
        assert 200 == allowed.status_code


def test_internal_task_cancel_requires_csrf(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        task = client.app.state.task_queue.enqueue(
            TaskCreate(
                task_type="test",
                title="Internal cancel",
                idempotency_scope="test",
                idempotency_key="internal-cancel",
            )
        )

        denied = client.post(f"/internal/tasks/{task.id}/cancel")
        allowed = client.post(
            f"/internal/tasks/{task.id}/cancel",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
        )

        assert 403 == denied.status_code
        assert 200 == allowed.status_code
        assert f"/tasks/{task.id}" == allowed.json()["location"]


def test_interrupted_task_recovery_requires_csrf_and_explicit_action(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        queue = client.app.state.task_queue
        task = queue.enqueue(
            TaskCreate(
                task_type="unregistered",
                title="Recoverable copy",
                idempotency_scope="copy",
                idempotency_key="recover",
                resumable=True,
                max_retries=1,
                recovery_strategy="retry_from_start",
            )
        )
        assert queue.claim_next("previous-process") is not None
        assert 1 == queue.recover_orphaned_on_startup()

        detail = client.get(f"/tasks/{task.id}")
        api_detail = client.get(f"/internal/tasks/{task.id}")
        denied = client.post(f"/internal/tasks/{task.id}/recover")
        allowed = client.post(
            f"/internal/tasks/{task.id}/recover",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
        )

        assert 'id="nexora-root"' in detail.text
        assert "interrupted" == api_detail.json()["task"]["status"]
        assert api_detail.json()["task"]["resumable"]
        assert 403 == denied.status_code
        assert 200 == allowed.status_code
        with client.app.state.database.session() as session:
            stored = session.get(type(task), task.id)
            assert stored is not None
            assert TaskStatus.QUEUED == stored.status
