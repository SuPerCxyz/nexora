from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.remote.executor import RemoteCommandAudit, RemoteExecutor
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile
from nexora.resources.conflicts import (
    ResourceBaseVersion,
    ResourceWriteConflict,
    ResourceWriteGuard,
)
from nexora.resources.domain_parser import parse_domain_observation
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlan, VmChangePlanStatus
from nexora.vms.cpu_changes import VmChangeError, VmCpuChangeService
from nexora.vms.memory_changes import VmMemoryChangeService
from nexora.xml import CpuTopologyChange, LibvirtXmlDocument, MemoryConfigChange

DOMAIN_UUID = "11111111-1111-1111-1111-111111111111"
DOMAIN_XML = b"""<domain type="kvm" xmlns:vendor="urn:vendor">
  <name>vm-one</name>
  <uuid>11111111-1111-1111-1111-111111111111</uuid>
  <metadata><vendor:policy mode="keep"/></metadata>
  <memory unit="KiB">4194304</memory>
  <vcpu current="2">4</vcpu>
  <cpu mode="host-passthrough">
    <topology sockets="1" dies="1" clusters="1" cores="2" threads="2"/>
    <vendor:extension enabled="yes"/>
  </cpu>
  <devices/>
</domain>"""


class Resolver:
    def __init__(self, known_hosts: Path) -> None:
        self.known_hosts = known_hosts

    def resolve(self, _host_id: str) -> SSHConnectionProfile:
        return SSHConnectionProfile(SSHConnection("node", 22, "root", self.known_hosts))


class Audit:
    def record(self, _event: RemoteCommandAudit) -> None:
        return


class CpuBackend:
    def __init__(self, state: dict[str, bytes], *, ignore_first_define: bool = False) -> None:
        self.state = state
        self.ignore_first_define = ignore_first_define
        self.define_calls = 0
        self.commands: list[str] = []

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
        self.commands.append(command)
        if " domcapabilities" in command:
            return ProcessResult(
                0,
                b"<domainCapabilities><path>/usr/bin/qemu-system-x86_64</path>"
                b"</domainCapabilities>",
                b"",
                False,
                False,
                False,
                False,
                0.01,
            )
        if " virsh " in f" {command} " and " define " in f" {command} ":
            self.define_calls += 1
            if not (self.ignore_first_define and self.define_calls == 1):
                assert stdin is not None
                self.state["xml"] = stdin
        return ProcessResult(0, b"", b"", False, False, False, False, 0.01)


class Discovery:
    def __init__(self, state: dict[str, bytes]) -> None:
        self.state = state

    def read_one(self, _host_id: str, _vm_uuid: str):
        observation = parse_domain_observation(
            DOMAIN_UUID,
            self.state["xml"],
            None,
            state="shut off",
            autostart=False,
        )
        return replace(
            observation,
            details={**observation.details, "active": False, "managed_save": False},
        )


def test_cpu_preview_confirm_and_apply_preserve_unknown_xml(settings: Settings) -> None:
    database, service, state, backend, base = _runtime(settings)
    change = CpuTopologyChange(4, 8, 1, 1, 1, 4, 2)

    preview = service.preview(base, change)
    assert 'current="2"' in preview.plan.diff_text
    assert 'current="4"' in preview.plan.diff_text
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=DOMAIN_UUID,
    )
    result = service.execute(preview.plan.id, task_id="task-cpu")

    assert "reboot_required=true" in result
    assert any("virt-xml-validate - domain" in item for item in backend.commands)
    assert any("define /dev/stdin --validate" in item for item in backend.commands)
    document = LibvirtXmlDocument.parse(state["xml"])
    assert document.root.find("metadata/{urn:vendor}policy") is not None
    assert document.root.find("cpu/{urn:vendor}extension") is not None
    with database.session() as session:
        plan = session.get(VmChangePlan, preview.plan.id)
        resource = session.get(ResourceIndex, base.resource_id)
        assert plan is not None and plan.status == VmChangePlanStatus.SUCCEEDED
        assert resource is not None and resource.status == ResourceStatus.MANAGED
        assert preview.plan.proposed_persistent_hash == resource.persistent_hash
    database.dispose()


def test_cpu_preview_rejects_out_of_band_change(settings: Settings) -> None:
    database, service, state, backend, base = _runtime(settings)
    state["xml"] = DOMAIN_XML.replace(b"<memory ", b'<memory dumpCore="on" ')

    with pytest.raises(ResourceWriteConflict):
        service.preview(base, CpuTopologyChange(4, 8, 1, 1, 1, 4, 2))

    assert not backend.commands
    database.dispose()


def test_cpu_confirmation_token_is_scope_bound(settings: Settings) -> None:
    database, service, _state, _backend, base = _runtime(settings)
    preview = service.preview(base, CpuTopologyChange(4, 8, 1, 1, 1, 4, 2))

    with pytest.raises(VmChangeError, match="invalid"):
        service.confirm(
            preview.plan.id,
            "wrong-token",
            host_id="host-1",
            vm_uuid=DOMAIN_UUID,
        )

    database.dispose()


def test_cpu_apply_verification_failure_rolls_back_original_xml(settings: Settings) -> None:
    database, service, state, backend, base = _runtime(settings, ignore_first_define=True)
    preview = service.preview(base, CpuTopologyChange(4, 8, 1, 1, 1, 4, 2))
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=DOMAIN_UUID,
    )

    with pytest.raises(ValueError, match="does not match"):
        service.execute(preview.plan.id, task_id="task-rollback")

    assert 2 == backend.define_calls
    assert DOMAIN_XML == state["xml"]
    with database.session() as session:
        plan = session.get(VmChangePlan, preview.plan.id)
        assert plan is not None and plan.status == VmChangePlanStatus.FAILED
        assert plan.error_message is not None
    database.dispose()


def test_memory_change_reuses_confirmed_xml_plan_and_preserves_unknown(
    settings: Settings,
) -> None:
    database, cpu_service, state, _backend, base = _runtime(settings)
    service = VmMemoryChangeService(
        database,
        cpu_service.executor,
        cpu_service.discovery,
        cpu_service.store,
        cpu_service.guard,
        cpu_service.locks,
    )
    change = MemoryConfigChange(
        6 * 1024 * 1024,
        8 * 1024 * 1024,
        hugepages=True,
        locked=True,
        source_type="memfd",
        access_mode="shared",
        allocation_mode="immediate",
        discard=True,
    )

    preview = service.preview_memory(base, change)
    service.confirm(
        preview.plan.id,
        preview.confirmation_token,
        host_id="host-1",
        vm_uuid=DOMAIN_UUID,
    )
    result = service.execute(preview.plan.id, task_id="task-memory")

    assert "memory_config updated" in result
    document = LibvirtXmlDocument.parse(state["xml"])
    assert str(8 * 1024 * 1024) == document.root.findtext("memory")
    assert document.root.find("metadata/{urn:vendor}policy") is not None
    assert document.root.find("memoryBacking/hugepages") is not None
    database.dispose()


def _runtime(
    settings: Settings,
    *,
    ignore_first_define: bool = False,
) -> tuple[
    Database,
    VmCpuChangeService,
    dict[str, bytes],
    CpuBackend,
    ResourceBaseVersion,
]:
    database = Database(settings)
    upgrade_database(database)
    _add_host(database)
    state = {"xml": DOMAIN_XML}
    store = ResourceIndexStore(database)
    discovery = Discovery(state)
    result = store.apply_snapshot(
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        [discovery.read_one("host-1", DOMAIN_UUID)],
    )
    resource = result.resources[0]
    base = ResourceBaseVersion(
        resource.id,
        "host-1",
        ResourceType.VIRTUAL_MACHINE,
        DOMAIN_UUID,
        result.generation,
        resource.persistent_hash,
        resource.live_hash,
    )
    backend = CpuBackend(state, ignore_first_define=ignore_first_define)
    service = VmCpuChangeService(
        database,
        RemoteExecutor(
            Resolver(settings.data_dir / "hostkeys" / "known_hosts"),
            Audit(),
            backend=backend,
        ),
        discovery,  # type: ignore[arg-type]
        store,
        ResourceWriteGuard(database),
        ResourceLockStore(database),
    )
    return database, service, state, backend, base


def _add_host(database: Database) -> None:
    now = datetime.now(UTC)
    with database.session() as session:
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
