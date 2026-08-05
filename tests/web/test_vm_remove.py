from types import SimpleNamespace

from fastapi.testclient import TestClient
from web.test_vms import DOMAIN_UUID, DOMAIN_XML, _initialize, _seed_vm

from nexora.app import create_app
from nexora.config import Settings
from nexora.resources.models import ResourceIndex
from nexora.web.security import CSRF_COOKIE


class RemoveServiceStub:
    def __init__(self, operation: str = "delete") -> None:
        self.operation = operation

    def preview(self, remove: object) -> object:
        plan = SimpleNamespace(
            id="remove-plan",
            operation=self.operation,
            diff_text="+ undefine",
        )
        return SimpleNamespace(plan=plan, confirmation_token="confirmation")

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
        confirmation_name: str,
    ) -> object:
        assert ("remove-plan", "confirmation") == (plan_id, token)
        assert "existing-vm" == confirmation_name
        return SimpleNamespace(
            id=plan_id,
            host_id=host_id,
            vm_uuid=vm_uuid,
            vm_name="existing-vm",
            operation=self.operation,
        )


def test_internal_vm_delete_preview_requires_name_and_queues_task(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        client.app.state.vm_remove_service = RemoveServiceStub("delete")
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        assert (
            403
            == client.post(
                f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/remove/preview",
                json={"operation": "delete"},
            ).status_code
        )

        preview = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/remove/preview",
            headers=headers,
            json={"operation": "delete", "remove_disks": True},
        )
        assert 200 == preview.status_code
        payload = preview.json()
        assert "delete" == payload["operation"]
        assert payload["remove_disks"] is True
        assert "undefine" in payload["diff_text"]

        client.app.state.task_coordinator.stop()
        applied = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/remove/apply",
            headers=headers,
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
                "confirmation_name": "existing-vm",
            },
        )
        assert 201 == applied.status_code
        assert applied.json()["location"].startswith("/tasks/")


def test_internal_vm_rename_preview_and_queue(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        client.app.state.vm_remove_service = RemoveServiceStub("rename")
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        preview = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/remove/preview",
            headers=headers,
            json={"operation": "rename", "target_name": "renamed-vm"},
        )
        assert 200 == preview.status_code
        payload = preview.json()
        assert "rename" == payload["operation"]
        assert "renamed-vm" == payload["target_name"]

        client.app.state.task_coordinator.stop()
        applied = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/remove/apply",
            headers=headers,
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
                "confirmation_name": "existing-vm",
            },
        )
        assert 201 == applied.status_code


def test_internal_vm_delete_requires_wrong_name_rejected(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        stub = RemoveServiceStub("delete")

        def reject(*args: object, **kwargs: object) -> object:
            raise ValueError("VM name confirmation is invalid")

        stub.confirm = reject  # type: ignore[method-assign]
        client.app.state.vm_remove_service = stub
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        client.app.state.task_coordinator.stop()

        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/remove/apply",
            headers=headers,
            json={
                "plan_id": "remove-plan",
                "confirmation_token": "confirmation",
                "confirmation_name": "wrong-name",
            },
        )
        assert 409 == response.status_code


def test_remove_service_delete_executes_undefine_and_verifies(settings: Settings) -> None:

    from nexora.remote.process import ProcessResult
    from nexora.remote.ssh import SSHConnection, SSHConnectionProfile
    from nexora.vms.remove_contracts import VmRemoveInput
    from nexora.vms.remove_service import VmRemoveService

    class Backend:
        def __init__(self) -> None:
            self.removed = False

        def run(
            self,
            _profile: SSHConnectionProfile,
            command: str,
            *,
            timeout: int,
            stdin: bytes | None,
            cancel_event: object,
        ) -> ProcessResult:
            del timeout, stdin, cancel_event
            if self.removed:
                return ProcessResult(0, b"", b"", False, False, False, False, 0.01)
            if " undefine " in command:
                self.removed = True
                return ProcessResult(0, b"", b"", False, False, False, False, 0.01)
            if " dominfo " in command:
                return ProcessResult(
                    0,
                    (
                        b"Id: -\nState: shut off\nPersistent: yes\nAutostart: disable\n"
                        b"Managed save: no\n"
                    ),
                    b"",
                    False,
                    False,
                    False,
                    False,
                    0.01,
                )
            if " dumpxml " in command:
                return ProcessResult(0, DOMAIN_XML, b"", False, False, False, False, 0.01)
            if " snapshot-list " in command:
                return ProcessResult(0, b"", b"", False, False, False, False, 0.01)
            if " list --all --uuid" in command:
                return ProcessResult(0, b"", b"", False, False, False, False, 0.01)
            raise AssertionError(command)

    from pathlib import Path

    class Resolver:
        def resolve(self, _host_id: str) -> SSHConnectionProfile:
            return SSHConnectionProfile(SSHConnection("node", 22, "root", Path("/tmp/known_hosts")))

    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        backend = Backend()
        client.app.state.remote_executor.resolver = Resolver()
        client.app.state.remote_executor.backend = backend
        client.app.state.task_coordinator.stop()

        with client.app.state.database.session() as session:
            resource = session.query(ResourceIndex).filter_by(native_id=DOMAIN_UUID).one()

        service: VmRemoveService = client.app.state.vm_remove_service
        remove = VmRemoveInput(
            host_id="host-1",
            resource_id=resource.id,
            vm_uuid=DOMAIN_UUID,
            vm_name=resource.display_name,
            generation=resource.observed_generation,
            persistent_hash=resource.persistent_hash,
            operation="delete",
            remove_disks=False,
            remove_nvram=False,
        )
        preview = service.preview(remove)
        plan = service.confirm(
            preview.plan.id,
            preview.confirmation_token,
            host_id="host-1",
            vm_uuid=DOMAIN_UUID,
            confirmation_name="existing-vm",
        )
        summary = service.execute(plan.id, task_id="task-remove")
        assert "VM deleted" in summary
        assert backend.removed
