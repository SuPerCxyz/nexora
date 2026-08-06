import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from nexora.app import create_app
from nexora.config import Settings
from nexora.hosts.models import AuthenticationMethod, Host, HostCapability, HostStatus, SudoMode
from nexora.resources.models import ResourceDocument, ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.models import Task, TaskStatus
from nexora.web.security import PREAUTH_CSRF_COOKIE

VM_UUID = "11111111-1111-1111-1111-111111111111"


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


def _seed_core_resources(client: TestClient) -> None:
    now = datetime.now(UTC)
    with client.app.state.database.session() as session:
        session.add(
            Host(
                id="host-1",
                name="node-one",
                address="192.0.2.10",
                ssh_port=22,
                ssh_username="root",
                authentication_method=AuthenticationMethod.PRIVATE_KEY,
                sudo_mode=SudoMode.NONE,
                libvirt_uri="qemu:///system",
                status=HostStatus.READY,
                labels_json='["production"]',
                created_at=now,
                updated_at=now,
                last_scanned_at=now,
            )
        )
        vm = ResourceIndex(
            id="vm-resource-1",
            host_id="host-1",
            resource_type=ResourceType.VIRTUAL_MACHINE,
            native_id=VM_UUID,
            display_name="web-01",
            status=ResourceStatus.MANAGED,
            source="libvirt",
            observed_generation=1,
            details_json=json.dumps(
                {
                    "state": "running",
                    "active": True,
                    "persistent": True,
                    "autostart": True,
                    "current_vcpus": 4,
                    "maximum_vcpus": 8,
                    "memory_kib": 2097152,
                    "disks": [
                        {
                            "type": "file",
                            "device": "disk",
                            "source": "/images/web.qcow2",
                            "target": "vda",
                            "bus": "virtio",
                            "format": "qcow2",
                        }
                    ],
                    "interfaces": [
                        {
                            "type": "bridge",
                            "source": "br0",
                            "mac": "52:54:00:12:34:56",
                            "model": "virtio",
                        }
                    ],
                    "host_devices": [
                        {
                            "type": "pci",
                            "mode": "subsystem",
                            "address": {
                                "domain": "0x0000",
                                "bus": "0x05",
                                "slot": "0x00",
                                "function": "0x0",
                            },
                        }
                    ],
                }
            ),
            labels_json="[]",
            first_seen_at=now,
            last_seen_at=now,
        )
        interface = ResourceIndex(
            id="interface-resource-1",
            host_id="host-1",
            resource_type=ResourceType.HOST_INTERFACE,
            native_id="2",
            display_name="eno1",
            status=ResourceStatus.READ_ONLY,
            source="ip",
            observed_generation=1,
            details_json=json.dumps(
                {
                    "kind": "physical",
                    "mac": "00:11:22:33:44:55",
                    "operstate": "UP",
                    "routes": [{"dst": "default"}],
                }
            ),
            labels_json="[]",
            first_seen_at=now,
            last_seen_at=now,
        )
        pci_device = ResourceIndex(
            id="pci-resource-1",
            host_id="host-1",
            resource_type=ResourceType.PCI_DEVICE,
            native_id="0000:05:00.0",
            display_name="pci_0000_05_00_0",
            status=ResourceStatus.READ_ONLY,
            source="udev",
            observed_generation=1,
            details_json=json.dumps(
                {
                    "vendor": "Intel Corporation",
                    "product": "I211 Gigabit Network Connection",
                    "class": "0x020000",
                    "driver": "vfio-pci",
                    "iommu_group": "17",
                }
            ),
            labels_json="[]",
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add_all((vm, interface, pci_device))
        session.add_all(
            (
                _capability("tool.virsh", "normal", "/usr/bin/virsh", now),
                _capability("libvirt.version", "normal", "libvirt 10", now),
                _capability("system.lscpu", "normal", {"model_name": "Example CPU"}, now),
                _capability("libvirt.nodeinfo", "normal", {"memory_kib": 32768}, now),
            )
        )
        session.flush()
        session.add(
            ResourceDocument(
                resource_index_id=vm.id,
                document_kind="persistent_xml",
                content=b"<domain><name>web-01</name></domain>",
                content_hash="0" * 64,
                hash_algorithm="test",
                observed_at=now,
            )
        )
        session.commit()


def _capability(
    key: str,
    status: str,
    value: object,
    observed_at: datetime,
) -> HostCapability:
    return HostCapability(
        host_id="host-1",
        capability_key=key,
        status=status,
        value_json=json.dumps(value),
        observed_at=observed_at,
    )


def test_core_internal_apis_require_authentication(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        for path in ("/internal/overview", "/internal/hosts", "/internal/vms"):
            response = client.get(path)
            assert 401 == response.status_code
            assert "authentication_required" == response.json()["code"]
            assert "no-store" == response.headers["cache-control"]


def test_overview_returns_local_status_summary(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_core_resources(client)
        response = client.get("/internal/overview")

    assert 200 == response.status_code
    assert {
        "host_total": 1,
        "host_ready": 1,
        "host_synced": 1,
        "vm_total": 1,
        "vm_running": 1,
        "vm_paused": 0,
        "vm_stopped": 0,
        "active_tasks": 0,
        "task_pending": 0,
        "failed_tasks": 0,
        "storage_pool_total": 0,
        "storage_volume_total": 0,
    } == response.json()
    assert "no-store" == response.headers["cache-control"]


def test_host_list_is_paginated_and_bounded(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_core_resources(client)
        response = client.get("/internal/hosts?page=1&page_size=1")
        rejected = client.get("/internal/hosts?page_size=101")

    assert 200 == response.status_code
    assert 1 == response.json()["total"]
    assert {
        "id": "host-1",
        "name": "node-one",
        "address": "192.0.2.10",
        "ssh_port": 22,
        "status": "ready",
        "labels": ["production"],
        "last_scanned_at": response.json()["items"][0]["last_scanned_at"],
    } == response.json()["items"][0]
    assert 422 == rejected.status_code


def test_vm_list_returns_display_fields_without_xml(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_core_resources(client)
        response = client.get("/internal/vms?page=1&page_size=20")

    assert 200 == response.status_code
    payload = response.json()
    assert 1 == payload["total"]
    assert {
        "resource_id": "vm-resource-1",
        "host_id": "host-1",
        "native_id": VM_UUID,
        "name": "web-01",
        "host_name": "node-one",
        "state": "running",
        "status": "managed",
        "vcpus": 4,
        "memory_mib": 2048,
        "last_seen_at": payload["items"][0]["last_seen_at"],
        "needs_restart": False,
    } == payload["items"][0]
    assert "xml" not in response.text.lower()


def test_vm_list_filters_by_state_and_host(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_core_resources(client)
        with client.app.state.database.session() as session:
            session.add(
                ResourceIndex(
                    id="vm-resource-2",
                    host_id="host-1",
                    resource_type=ResourceType.VIRTUAL_MACHINE,
                    native_id="22222222-2222-2222-2222-222222222222",
                    display_name="web-02",
                    status=ResourceStatus.MANAGED,
                    source="libvirt",
                    observed_generation=1,
                    details_json=json.dumps(
                        {"state": "shut off", "active": False, "persistent": True}
                    ),
                    labels_json="[]",
                    first_seen_at=datetime.now(UTC),
                    last_seen_at=datetime.now(UTC),
                )
            )
        running = client.get("/internal/vms", params={"state": "running"})
        stopped = client.get("/internal/vms", params={"state": "shut off"})
        filtered = client.get(
            "/internal/vms", params={"state": "shut off", "host_id": "host-1"}
        )
        unknown_host = client.get("/internal/vms", params={"host_id": "missing-host"})

    assert 200 == running.status_code
    assert 1 == running.json()["total"]
    assert "web-01" == running.json()["items"][0]["name"]
    assert 1 == stopped.json()["total"]
    assert "web-02" == stopped.json()["items"][0]["name"]
    assert 1 == filtered.json()["total"]
    assert 0 == unknown_host.json()["total"]


def test_vm_list_needs_restart_flips_after_config_change_task(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_core_resources(client)
        now = datetime.now(UTC)
        with client.app.state.database.session() as session:
            session.add(
                Task(
                    id="task-config",
                    task_type="vm.cpu_change",
                    host_id="host-1",
                    vm_uuid=VM_UUID,
                    operation_id="op-config",
                    idempotency_scope="vm:host-1:" + VM_UUID + ":cpu",
                    idempotency_key="plan-config",
                    title="更新 CPU",
                    status=TaskStatus.SUCCEEDED,
                    resumable=False,
                    recovery_strategy="verify_only",
                    created_at=now,
                    started_at=now,
                    finished_at=now + timedelta(seconds=1),
                )
            )
            session.add(
                Task(
                    id="task-start",
                    task_type="vm.lifecycle",
                    host_id="host-1",
                    vm_uuid=VM_UUID,
                    operation_id="op-start",
                    idempotency_scope="vm:host-1:" + VM_UUID + ":lifecycle",
                    idempotency_key="lifecycle-start",
                    title="启动",
                    input_summary='{"action":"start"}',
                    status=TaskStatus.SUCCEEDED,
                    resumable=False,
                    recovery_strategy="verify_only",
                    created_at=now - timedelta(minutes=5),
                    started_at=now - timedelta(minutes=5),
                    finished_at=now - timedelta(minutes=4),
                )
            )
            session.commit()
        response = client.get("/internal/vms?page=1&page_size=20")

    assert 200 == response.status_code
    assert True is response.json()["items"][0]["needs_restart"]


def test_vm_list_needs_restart_false_when_start_is_later_than_config(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_core_resources(client)
        now = datetime.now(UTC)
        with client.app.state.database.session() as session:
            session.add(
                Task(
                    id="task-config-2",
                    task_type="vm.cpu_change",
                    host_id="host-1",
                    vm_uuid=VM_UUID,
                    operation_id="op-config-2",
                    idempotency_scope="vm:host-1:" + VM_UUID + ":cpu",
                    idempotency_key="plan-config-2",
                    title="更新 CPU",
                    status=TaskStatus.SUCCEEDED,
                    resumable=False,
                    recovery_strategy="verify_only",
                    created_at=now - timedelta(minutes=5),
                    started_at=now - timedelta(minutes=5),
                    finished_at=now - timedelta(minutes=4),
                )
            )
            session.add(
                Task(
                    id="task-start-2",
                    task_type="vm.lifecycle",
                    host_id="host-1",
                    vm_uuid=VM_UUID,
                    operation_id="op-start-2",
                    idempotency_scope="vm:host-1:" + VM_UUID + ":lifecycle",
                    idempotency_key="lifecycle-start-2",
                    title="启动",
                    input_summary='{"action":"start"}',
                    status=TaskStatus.SUCCEEDED,
                    resumable=False,
                    recovery_strategy="verify_only",
                    created_at=now,
                    started_at=now,
                    finished_at=now + timedelta(seconds=1),
                )
            )
            session.commit()
        response = client.get("/internal/vms?page=1&page_size=20")

    assert 200 == response.status_code
    assert False is response.json()["items"][0]["needs_restart"]


def test_host_detail_returns_bounded_local_resources(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_core_resources(client)
        response = client.get("/internal/hosts/host-1")

    assert 200 == response.status_code
    payload = response.json()
    assert "node-one" == payload["host"]["name"]
    assert "qemu:///system" == payload["libvirt_uri"]
    assert 1 == payload["resource_counts"]["virtual_machine"]
    assert "web-01" == payload["virtual_machines"][0]["name"]
    assert "Example CPU" == payload["hardware"]["cpu_model"]
    assert "00:11:22:33:44:55" == payload["network_adapters"][0]["mac"]
    assert "supported" == payload["features"][0]["status"]
    pcie = next(item for item in payload["features"] if item["key"] == "pcie_passthrough")
    assert "supported" == pcie["status"]
    assert "已发现 1 个可直通 PCIe 设备" == pcie["description"]
    assert "capabilities" not in payload
    assert "/manage/hosts/host-1" == payload["manage_url"]
    assert "no-store" == response.headers["cache-control"]


def test_vm_detail_returns_devices_metrics_and_safe_xml(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_core_resources(client)
        response = client.get(f"/internal/hosts/host-1/vms/{VM_UUID}")
        configuration = client.get(f"/internal/hosts/host-1/vms/{VM_UUID}/configuration")
        guest_agent = client.get(f"/internal/hosts/host-1/vms/{VM_UUID}/guest-agent")
        with client.app.state.database.session() as session:
            document = session.scalar(select(ResourceDocument))
            assert document is not None
            document.content = b'<!DOCTYPE domain [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><domain>&xxe;</domain>'
        unsafe_xml = client.get(f"/internal/hosts/host-1/vms/{VM_UUID}")

    assert 200 == response.status_code
    payload = response.json()
    assert "web-01" == payload["vm"]["name"]
    assert 8 == payload["maximum_vcpus"]
    assert "vda" == payload["disks"][0]["target"]
    assert "br0" == payload["interfaces"][0]["source"]
    assert {
        "type": "pci",
        "address": "0000:05:00.0",
        "category": "网卡",
        "name": "Intel Corporation · I211 Gigabit Network Connection",
        "driver": "vfio-pci",
        "iommu_group": "17",
    } == payload["host_devices"][0]
    assert "<domain>\n  <name>web-01</name>\n</domain>" in payload["xml"]
    assert [] == payload["snapshots"]
    assert [] == payload["metrics"]
    assert "no-store" == response.headers["cache-control"]
    assert 200 == configuration.status_code
    assert "web-01" == configuration.json()["vm"]["name"]
    assert "0000:05:00.0" == configuration.json()["host_devices"][0]["address"]
    assert "no-store" == configuration.headers["cache-control"]
    assert 200 == guest_agent.status_code
    assert "not_configured" == guest_agent.json()["state"]
    assert guest_agent.json()["channel_configured"] is False
    assert "" == unsafe_xml.json()["xml"]
    assert "DOCTYPE" not in unsafe_xml.text


def test_internal_details_return_structured_not_found(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host = client.get("/internal/hosts/missing")
        vm = client.get(f"/internal/hosts/missing/vms/{VM_UUID}")

    assert (404, "host_not_found") == (host.status_code, host.json()["code"])
    assert (404, "vm_not_found") == (vm.status_code, vm.json()["code"])
