import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from fastapi.testclient import TestClient
from sqlalchemy import select

from nexora.app import create_app
from nexora.config import Settings
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile
from nexora.resources.domain_parser import parse_domain_observation
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.resources.snapshot_parser import parse_snapshot_observation
from nexora.tasks.models import Task, TaskStatus
from nexora.vms.change_models import VmChangePlan
from nexora.web.security import CSRF_COOKIE, PREAUTH_CSRF_COOKIE

DOMAIN_UUID = "11111111-1111-1111-1111-111111111111"
DOMAIN_XML = f"""\
<domain type="kvm"><name>existing-vm</name><uuid>{DOMAIN_UUID}</uuid>
<memory unit="KiB">1048576</memory><vcpu>2</vcpu><devices/></domain>""".encode()


class Resolver:
    def __init__(self, known_hosts: Path) -> None:
        self.known_hosts = known_hosts

    def resolve(self, _host_id: str) -> SSHConnectionProfile:
        return SSHConnectionProfile(SSHConnection("node", 22, "root", self.known_hosts))


class VmBackend:
    def __init__(self) -> None:
        self.state = "shut off"
        self.active = False
        self.xml = DOMAIN_XML

    def run(
        self,
        _profile: SSHConnectionProfile,
        command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult:
        del timeout, cancel_event
        if " dominfo " in command:
            output = (
                f"Id: {'1' if self.active else '-'}\nState: {self.state}\n"
                "Persistent: yes\nAutostart: disable\nManaged save: no\n"
            ).encode()
        elif " dumpxml " in command:
            output = self.xml
        elif " snapshot-list " in command or "virt-xml-validate - domain" in command:
            output = b""
        elif " define /dev/stdin --validate" in command:
            assert stdin is not None
            self.xml = stdin
            output = b""
        elif f" start {DOMAIN_UUID}" in command:
            self.state = "running"
            self.active = True
            output = b""
        else:
            raise AssertionError(command)
        return ProcessResult(0, output, b"", False, False, False, False, 0.01)


def test_vm_pages_and_start_lifecycle_task_use_node_scoped_identity(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        backend = VmBackend()
        client.app.state.remote_executor.resolver = Resolver(
            settings.data_dir / "hostkeys" / "known_hosts"
        )
        client.app.state.remote_executor.backend = backend

        listing = client.get("/vms")
        detail = client.get(f"/hosts/host-1/vms/{DOMAIN_UUID}")

        assert 200 == listing.status_code
        assert 'id="nexora-root"' in listing.text
        vm_api = client.get("/internal/vms")
        detail_api = client.get(f"/internal/hosts/host-1/vms/{DOMAIN_UUID}")
        assert "existing-vm" == vm_api.json()["items"][0]["name"]
        assert 200 == detail.status_code
        assert DOMAIN_UUID == detail_api.json()["vm"]["native_id"]
        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/lifecycle",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={"action": "start"},
            follow_redirects=False,
        )
        assert 201 == response.status_code
        task_id = response.json()["task_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with client.app.state.database.session() as session:
                task = session.get(Task, task_id)
                if task is not None and task.status == TaskStatus.SUCCEEDED:
                    break
            time.sleep(0.01)
        else:
            raise AssertionError("VM start task did not complete")
        assert "running" == backend.state
        with client.app.state.database.session() as session:
            stored = session.scalar(
                select(ResourceIndex).where(
                    ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE
                )
            )
            assert stored is not None
            assert "running" == json.loads(stored.details_json)["state"]


def test_internal_vm_lifecycle_uses_current_resource_version(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        resource = _seed_vm(client)
        client.app.state.task_coordinator.stop()

        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/lifecycle",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={"action": "start"},
        )

        assert 201 == response.status_code
        assert response.json()["location"].startswith("/tasks/")
        with client.app.state.database.session() as session:
            task = session.get(Task, response.json()["task_id"])
            assert task is not None
            assert "vm.lifecycle" == task.task_type
            payload = json.loads(task.input_summary or "{}")
            assert resource.id == payload["resource_id"]
            assert resource.observed_generation == payload["generation"]
            assert "start" == payload["action"]


def test_internal_vm_force_action_requires_name_confirmation(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        resource = _seed_vm(client)
        with client.app.state.database.session() as session:
            stored = session.get(ResourceIndex, resource.id)
            assert stored is not None
            details = json.loads(stored.details_json)
            stored.details_json = json.dumps({**details, "active": True, "state": "running"})

        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/lifecycle",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
            json={"action": "force_off"},
        )

        assert 409 == response.status_code
        assert "vm_name_mismatch" == response.json()["code"]


def test_vm_detail_shows_discovered_snapshot_and_escaped_xml(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        observation = parse_snapshot_observation(
            DOMAIN_UUID,
            "before-upgrade",
            b"<domainsnapshot><name>before-upgrade</name><state>shutoff</state>"
            b"<creationTime>1700000000</creationTime><memory snapshot='no'/>"
            b"<description>&lt;script&gt;unsafe&lt;/script&gt;</description>"
            b"<disks><disk name='vda' snapshot='internal'/></disks>"
            + DOMAIN_XML
            + b"</domainsnapshot>",
            current=True,
        )
        ResourceIndexStore(client.app.state.database).apply_snapshot(
            "host-1",
            ResourceType.SNAPSHOT,
            [observation],
        )

        response = client.get(f"/internal/hosts/host-1/vms/{DOMAIN_UUID}")

        assert 200 == response.status_code
        payload = response.json()
        snapshot = payload["snapshots"][0]
        assert "before-upgrade" == snapshot["name"]
        assert snapshot["disks"] == ["vda"]
        assert snapshot["memory"] == "no"
        assert "<script>unsafe</script>" not in snapshot["xml"]
        assert "&lt;script&gt;unsafe&lt;/script&gt;" in snapshot["xml"]


def test_cpu_change_requires_preview_then_runs_persistent_task(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        backend = VmBackend()
        client.app.state.remote_executor.resolver = Resolver(
            settings.data_dir / "hostkeys" / "known_hosts"
        )
        client.app.state.remote_executor.backend = backend

        detail = client.get(f"/hosts/host-1/vms/{DOMAIN_UUID}")
        assert 200 == detail.status_code
        assert 'id="nexora-root"' in detail.text
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        preview = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/preview",
            headers=headers,
            json={
                "operation": "cpu",
                "values": {
                    "current_vcpus": 4,
                    "maximum_vcpus": 4,
                    "sockets": 1,
                    "dies": 1,
                    "clusters": 1,
                    "cores": 2,
                    "threads": 2,
                },
            },
        )
        assert 200 == preview.status_code
        payload = preview.json()
        assert "cpu_topology" == payload["change_type"]
        plan_id = payload["plan_id"]
        token = payload["confirmation_token"]
        response = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/apply",
            headers=headers,
            json={
                "plan_id": plan_id,
                "confirmation_token": token,
                "change_type": "cpu_topology",
            },
        )
        assert 201 == response.status_code
        task_id = response.json()["task_id"]
        _wait_for_success(client, task_id)
        with client.app.state.database.session() as session:
            plan = session.get(VmChangePlan, plan_id)
            assert plan is not None and plan.status == "succeeded"
        assert b'current="4">4</vcpu>' in backend.xml


def test_memory_change_previews_via_internal_json(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_vm(client)
        backend = VmBackend()
        client.app.state.remote_executor.resolver = Resolver(
            settings.data_dir / "hostkeys" / "known_hosts"
        )
        client.app.state.remote_executor.backend = backend

        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        preview = client.post(
            f"/internal/hosts/host-1/vms/{DOMAIN_UUID}/configuration/preview",
            headers=headers,
            json={
                "operation": "memory",
                "values": {
                    "current_mib": 1536,
                    "maximum_mib": 2048,
                    "hugepages": "on",
                    "locked": "on",
                    "source_type": "memfd",
                    "access_mode": "shared",
                    "allocation_mode": "immediate",
                    "discard": "on",
                },
            },
        )

        assert 200 == preview.status_code
        assert "memory_config" == preview.json()["change_type"]


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


def _seed_vm(client: TestClient) -> ResourceIndex:
    now = datetime.now(UTC)
    with client.app.state.database.session() as session:
        session.add(
            Host(
                id="host-1",
                name="node",
                address="node.example.test",
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
    observation = parse_domain_observation(
        DOMAIN_UUID,
        DOMAIN_XML,
        None,
        state="shut off",
        autostart=False,
    )
    observation = replace(
        observation,
        details={
            **observation.details,
            "active": False,
            "managed_save": False,
            "snapshot_names": [],
        },
    )
    return (
        ResourceIndexStore(client.app.state.database)
        .apply_snapshot(
            "host-1",
            ResourceType.VIRTUAL_MACHINE,
            [observation],
        )
        .resources[0]
    )


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
    raise AssertionError("VM CPU task did not complete")
