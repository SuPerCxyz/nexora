"""Web tests for VM XML configuration history and rollback routes."""

from fastapi.testclient import TestClient
from web.test_vms import DOMAIN_UUID, _initialize, _seed_vm

from nexora.app import create_app
from nexora.config import Settings
from nexora.web.security import CSRF_COOKIE


def _seed_history(client: TestClient, snapshot_id: str, xml: str) -> None:
    from nexora.vms.xml_history import VmXmlHistoryStore

    VmXmlHistoryStore(client.app.state.database).record(
        "host-1", DOMAIN_UUID, xml
    )
    with client.app.state.database.session() as session:
        from sqlalchemy import text as sql_text

        session.execute(
            sql_text(
                "UPDATE vm_xml_history SET id = :id "
                "WHERE host_id = :host_id AND vm_uuid = :vm_uuid"
            ),
            {"id": snapshot_id, "host_id": "host-1", "vm_uuid": DOMAIN_UUID},
        )
        session.commit()


def test_configuration_history_lists_owned_snapshots(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        _seed_history(
            client,
            "11111111-1111-4111-8111-111111111111",
            '<domain type="kvm"><name>existing-vm</name><vcpu>2</vcpu></domain>',
        )
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        response = client.get(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/history",
            headers=headers,
        )
        assert 200 == response.status_code
        items = response.json()["items"]
        assert 1 == len(items)
        assert "11111111-1111-4111-8111-111111111111" == items[0]["id"]


def test_configuration_rollback_enqueues_xml_restore_task(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        snapshot_id = "11111111-1111-4111-8111-111111111111"
        _seed_history(
            client,
            snapshot_id,
            '<domain type="kvm"><name>existing-vm</name><vcpu>2</vcpu></domain>',
        )
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        client.app.state.task_coordinator.stop()
        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/rollback",
            headers=headers,
            json={"history_id": snapshot_id},
        )
        assert 201 == response.status_code
        assert response.json()["location"].startswith("/tasks/")
        task_id = response.json()["task_id"]

        with client.app.state.database.session() as session:
            from sqlalchemy import select

            from nexora.tasks.models import Task

            task = session.scalar(select(Task).where(Task.id == task_id))
            assert task is not None
            assert "vm.xml_restore" == task.task_type
            assert snapshot_id == task.input_summary


def test_configuration_rollback_rejects_foreign_or_missing_snapshot(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        _seed_history(
            client,
            "11111111-1111-4111-8111-111111111111",
            '<domain type="kvm"><name>existing-vm</name><vcpu>2</vcpu></domain>',
        )
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/rollback",
            headers=headers,
            json={"history_id": "22222222-2222-4222-8222-222222222222"},
        )
        assert 404 == response.status_code
        assert "vm_history_not_found" == response.json()["code"]
