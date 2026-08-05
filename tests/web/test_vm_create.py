import json
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from web.test_storage import _seed_host, _seed_storage
from web.test_vm_disks import _seed_storage as _seed_vm_storage
from web.test_vms import _initialize, _seed_vm

from nexora.app import create_app
from nexora.config import Settings
from nexora.media.models import MediaItem, MediaStatus
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.vms.creation_contracts import VmImportCreateInput
from nexora.vms.media_creation_contracts import VmMediaCreateInput
from nexora.web.security import CSRF_COOKIE


class CreationServiceStub:
    def __init__(self) -> None:
        self.create: VmImportCreateInput | None = None

    def preview(self, create: object) -> object:
        if isinstance(create, VmImportCreateInput):
            self.create = create
        plan = SimpleNamespace(id="create-plan", diff_text="+ <domain/>")
        return SimpleNamespace(plan=plan, confirmation_token="confirmation")

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
    ) -> object:
        assert ("create-plan", "confirmation", "host-1") == (plan_id, token, host_id)
        return SimpleNamespace(
            id=plan_id,
            host_id=host_id,
            vm_uuid=vm_uuid,
            vm_name="new-vm",
        )


class NetworkCreationServiceStub(CreationServiceStub):
    def preview(self, create: VmImportCreateInput) -> object:
        assert "network" == create.network_kind
        assert "default" == create.network_name
        assert "install.iso" == create.iso_name
        return super().preview(create)


class MediaCreationServiceStub(CreationServiceStub):
    def __init__(self) -> None:
        self.create: VmMediaCreateInput | None = None

    def preview(self, create: VmMediaCreateInput) -> object:
        self.create = create
        plan = SimpleNamespace(id="media-plan", diff_text="+ <domain/>")
        return SimpleNamespace(
            plan=plan,
            confirmation_token="confirmation",
            target_path="/images/copied.qcow2",
        )

    def confirm(
        self,
        plan_id: str,
        token: str,
        *,
        host_id: str,
        vm_uuid: str,
    ) -> object:
        assert ("media-plan", "confirmation", "host-1") == (plan_id, token, host_id)
        return SimpleNamespace(
            id=plan_id,
            host_id=host_id,
            vm_uuid=vm_uuid,
            vm_name="media-vm",
        )


def test_vm_create_is_structured_preview_then_task(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        _seed_storage(client)
        client.app.state.vm_creation_service = CreationServiceStub()
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        page = client.get("/vms/create")
        assert 200 == page.status_code
        assert 'id="nexora-root"' in page.text
        assert 'name="path"' not in page.text
        preview = client.post(
            "/internal/vm-create/preview",
            headers=headers,
            json={
                "name": "new-vm",
                "memory_mib": 2048,
                "vcpus": 2,
                "volume_resource_id": "volume-1",
            },
        )
        assert 200 == preview.status_code
        payload = preview.json()
        assert "+ <domain/>" == payload["diff_text"]
        assert payload["vm_uuid"]

        client.app.state.task_coordinator.stop()
        response = client.post(
            "/internal/vm-create/apply",
            headers=headers,
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
                "host_id": payload["host_id"],
                "vm_uuid": payload["vm_uuid"],
            },
        )
        assert 201 == response.status_code
        assert response.json()["location"].startswith("/tasks/")


def test_vm_create_hides_volume_already_referenced_by_vm(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        vm = _seed_vm(client)
        _seed_vm_storage(client)
        with client.app.state.database.session() as session:
            resource = session.get(ResourceIndex, vm.id)
            assert resource is not None
            resource.details_json = (
                '{"state":"shut off","disks":[{"source":"/images/data.qcow2","format":"qcow2"}]}'
            )

        response = client.get("/internal/vm-create/options")

        assert 200 == response.status_code
        assert all(item["name"] != "data.qcow2" for item in response.json()["volumes"])


def test_vm_create_accepts_indexed_same_host_network_only(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        _seed_storage(client)
        _seed_network(client)
        _seed_iso(client)
        client.app.state.vm_creation_service = NetworkCreationServiceStub()

        options = client.get("/internal/vm-create/options").json()
        assert options["networks"] == [
            {
                "id": "network-1",
                "host_id": "host-1",
                "host_name": "node",
                "kind": "network",
                "name": "default",
            }
        ]
        assert options["isos"][0]["name"] == "install.iso"
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        preview = client.post(
            "/internal/vm-create/preview",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "network-vm",
                "memory_mib": 2048,
                "vcpus": 2,
                "volume_resource_id": "volume-1",
                "network_resource_id": "network-1",
                "iso_resource_id": "iso-1",
            },
        )
        assert 200 == preview.status_code
        assert "network / default" in preview.json()["summary"]["network"]
        assert "install.iso" == preview.json()["summary"]["iso_name"]


def test_vm_create_supports_uefi_without_secure_boot(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        _seed_storage(client)
        service = CreationServiceStub()
        client.app.state.vm_creation_service = service

        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        response = client.post(
            "/internal/vm-create/preview",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "uefi-vm",
                "memory_mib": 2048,
                "vcpus": 2,
                "volume_resource_id": "volume-1",
                "firmware": "uefi",
                "secure_boot": False,
            },
        )

        assert 200 == response.status_code
        assert service.create is not None
        assert "uefi" == service.create.firmware
        assert service.create.secure_boot is False


def test_internal_vm_create_preview_requires_csrf_and_creates_task(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        _seed_storage(client)
        service = CreationServiceStub()
        client.app.state.vm_creation_service = service
        submitted = {
            "name": "react-vm",
            "memory_mib": 2048,
            "vcpus": 2,
            "volume_resource_id": "volume-1",
            "firmware": "uefi",
            "secure_boot": False,
        }

        assert 403 == client.post("/internal/vm-create/preview", json=submitted).status_code
        headers = {"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)}
        preview = client.post(
            "/internal/vm-create/preview",
            json=submitted,
            headers=headers,
        )

        assert 200 == preview.status_code
        payload = preview.json()
        assert "uefi" == payload["summary"]["firmware"]
        assert payload["summary"]["secure_boot"] is False
        assert "+ <domain/>" == payload["diff_text"]

        client.app.state.task_coordinator.stop()
        applied = client.post(
            "/internal/vm-create/apply",
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
                "host_id": payload["host_id"],
                "vm_uuid": payload["vm_uuid"],
            },
            headers=headers,
        )
        assert 201 == applied.status_code
        assert applied.json()["location"].startswith("/tasks/")


def test_vm_create_from_platform_image_is_previewed_then_queued(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        _seed_storage(client)
        _seed_media(client)
        _seed_network(client)
        with client.app.state.database.session() as session:
            pool = session.get(ResourceIndex, "pool-1")
            assert pool is not None
            pool.details_json = json.dumps(
                {
                    "pool_type": "dir",
                    "active": True,
                    "state": "running",
                    "target_path": "/images",
                }
            )
        service = MediaCreationServiceStub()
        client.app.state.vm_media_creation_service = service

        page = client.get("/vms/create/platform-image")
        assert 200 == page.status_code
        assert 'id="nexora-root"' in page.text
        options = client.get("/internal/vm-create/platform-image/options").json()
        assert "base.qcow2" == options["media"][0]["file_name"]
        assert 'name="path"' not in page.text
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        guest_password = "web-test-guest-password"
        preview = client.post(
            "/internal/vm-create/platform-image/preview",
            headers=headers,
            json={
                "name": "media-vm",
                "memory_mib": 2048,
                "vcpus": 2,
                "media_item_id": "media-1",
                "pool_resource_id": "pool-1",
                "target_file_name": "copied.qcow2",
                "network_resource_id": "network-1",
                "cloud_init": True,
                "cloud_hostname": "media-vm.example.test",
                "cloud_username": "nexora",
                "cloud_ssh_public_key": "ssh-ed25519 " + "A" * 68,
                "cloud_password": guest_password,
                "cloud_password_confirmation": guest_password,
                "cloud_network_mode": "static",
                "cloud_ipv4_cidr": "192.0.2.20/24",
                "cloud_ipv4_gateway": "192.0.2.1",
                "cloud_dns_addresses": ["1.1.1.1", "9.9.9.9"],
                "target_capacity_gib": 1,
            },
        )
        assert 200 == preview.status_code
        payload = preview.json()
        assert "/images/copied.qcow2" == payload["summary"]["target_path"]
        assert "nexora@media-vm.example.test" in payload["summary"]["cloud_init"]
        assert guest_password not in payload["diff_text"]
        created = service.create
        assert created is not None
        assert created.cloud_password_hash is not None
        assert created.cloud_password_hash.startswith("$6$")
        assert ("1.1.1.1", "9.9.9.9") == created.cloud_dns_addresses
        assert 1024**3 == created.target_capacity_bytes
        client.app.state.task_coordinator.stop()
        response = client.post(
            "/internal/vm-create/platform-image/apply",
            headers=headers,
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
                "host_id": payload["host_id"],
                "vm_uuid": payload["vm_uuid"],
            },
        )
        assert 201 == response.status_code
        assert response.json()["location"].startswith("/tasks/")


def test_internal_platform_image_create_supports_uefi_without_secure_boot(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        _seed_host(client)
        _seed_storage(client)
        _seed_media(client)
        _seed_iso(client)
        with client.app.state.database.session() as session:
            pool = session.get(ResourceIndex, "pool-1")
            assert pool is not None
            pool.details_json = json.dumps(
                {
                    "pool_type": "dir",
                    "active": True,
                    "state": "running",
                    "target_path": "/images",
                }
            )
        service = MediaCreationServiceStub()
        client.app.state.vm_media_creation_service = service
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        preview = client.post(
            "/internal/vm-create/platform-image/preview",
            headers=headers,
            json={
                "name": "media-uefi-vm",
                "memory_mib": 2048,
                "vcpus": 2,
                "media_item_id": "media-1",
                "pool_resource_id": "pool-1",
                "target_file_name": "media-uefi.qcow2",
                "driver_iso_resource_id": "iso-1",
                "guest_profile": "windows",
                "firmware": "uefi",
                "secure_boot": False,
                "tpm2": True,
            },
        )

        assert 200 == preview.status_code
        payload = preview.json()
        assert "uefi" == payload["summary"]["firmware"]
        assert payload["summary"]["secure_boot"] is False
        assert "install.iso" == payload["summary"]["driver_iso_name"]
        assert service.create is not None
        assert "windows" == service.create.guest_profile
        assert service.create.secure_boot is False

        client.app.state.task_coordinator.stop()
        applied = client.post(
            "/internal/vm-create/platform-image/apply",
            headers=headers,
            json={
                "plan_id": payload["plan_id"],
                "confirmation_token": payload["confirmation_token"],
                "host_id": payload["host_id"],
                "vm_uuid": payload["vm_uuid"],
            },
        )
        assert 201 == applied.status_code
        assert applied.json()["location"].startswith("/tasks/")


def _seed_network(client: TestClient) -> None:
    now = datetime.now(UTC)
    with client.app.state.database.session() as session:
        session.add(
            ResourceIndex(
                id="network-1",
                host_id="host-1",
                resource_type=ResourceType.LIBVIRT_NETWORK,
                native_id="33333333-3333-3333-3333-333333333333",
                display_name="default",
                status=ResourceStatus.MANAGED,
                source="existing",
                persistent_hash="c" * 64,
                observed_generation=1,
                details_json=json.dumps(
                    {
                        "active": True,
                        "persistent": True,
                        "forward_mode": "nat",
                    }
                ),
                labels_json="[]",
                first_seen_at=now,
                last_seen_at=now,
            )
        )


def _seed_iso(client: TestClient) -> None:
    now = datetime.now(UTC)
    with client.app.state.database.session() as session:
        session.add(
            ResourceIndex(
                id="iso-1",
                host_id="host-1",
                resource_type=ResourceType.STORAGE_VOLUME,
                native_id='["11111111-1111-1111-1111-111111111111","/images/install.iso"]',
                parent_native_id="11111111-1111-1111-1111-111111111111",
                display_name="install.iso",
                status=ResourceStatus.MANAGED,
                source="existing",
                persistent_hash="d" * 64,
                observed_generation=1,
                details_json=json.dumps(
                    {
                        "key": "/images/install.iso",
                        "path": "/images/install.iso",
                        "format": "raw",
                        "capacity_bytes": 1024**2,
                    }
                ),
                labels_json="[]",
                first_seen_at=now,
                last_seen_at=now,
            )
        )


def _seed_media(client: TestClient) -> None:
    now = datetime.now(UTC)
    with client.app.state.database.session() as session:
        session.add(
            MediaItem(
                id="media-1",
                relative_path="images/base.qcow2",
                file_name="base.qcow2",
                kind="qcow2",
                status=MediaStatus.AVAILABLE,
                size_bytes=1024,
                modified_ns=1,
                file_device=1,
                file_inode=1,
                sha256="a" * 64,
                image_format="qcow2",
                virtual_size_bytes=512 * 1024**2,
                backing_chain_json="[]",
                observed_generation=1,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
