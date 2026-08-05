"""Structured persistent VM network interface attach, detach, and update plans."""

import json
from dataclasses import asdict
from io import BytesIO

from lxml import etree

from nexora.db import Database
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.contracts import ResourceObservation
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.change_models import VmChangePlan, VmChangePlanStatus
from nexora.vms.cpu_changes import (
    ChangeProgress,
    VmChangeConflict,
    VmChangeError,
    VmChangePreview,
    VmCpuChangeService,
    _uses_sudo,
)
from nexora.xml import (
    InterfaceAttachChange,
    InterfaceDetachChange,
    InterfaceUpdateChange,
    LibvirtXmlDocument,
    apply_interface_attach,
    apply_interface_detach,
    apply_interface_update,
    verify_interface_attach_result,
)


class VmNetworkChangeService(VmCpuChangeService):
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        discovery: DomainDiscoveryService,
        store: ResourceIndexStore,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
    ) -> None:
        super().__init__(database, executor, discovery, store, guard, locks)
        self._cached_plan: VmChangePlan | None = None

    def preview_attach(
        self,
        vm_base: ResourceBaseVersion,
        *,
        kind: str,
        source: str,
        model: str,
        mac: str | None = None,
        live: bool = False,
    ) -> VmChangePreview:
        self._refresh_domains(vm_base.host_id)
        current, original_xml, original_hash = self._current_persistent(vm_base)
        change = InterfaceAttachChange(kind, source, model, mac)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_interface_attach(proposed, change)
        change_input = {**asdict(change), "live": live}
        return self._create_preview(
            vm_base,
            "interface_attach",
            change_input,
            current,
            proposed,
            original_xml,
            original_hash,
        )

    def preview_detach(
        self,
        vm_base: ResourceBaseVersion,
        *,
        mac: str,
        live: bool = False,
    ) -> VmChangePreview:
        self._refresh_domains(vm_base.host_id)
        current, original_xml, original_hash = self._current_persistent(vm_base)
        change = InterfaceDetachChange(mac)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_interface_detach(proposed, change)
        change_input = {**asdict(change), "live": live}
        return self._create_preview(
            vm_base,
            "interface_detach",
            change_input,
            current,
            proposed,
            original_xml,
            original_hash,
        )

    def preview_update(
        self,
        vm_base: ResourceBaseVersion,
        *,
        mac: str,
        kind: str | None = None,
        source: str | None = None,
        model: str | None = None,
        new_mac: str | None = None,
        live: bool = False,
    ) -> VmChangePreview:
        self._refresh_domains(vm_base.host_id)
        current, original_xml, original_hash = self._current_persistent(vm_base)
        change = InterfaceUpdateChange(mac, kind, source, model, new_mac)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_interface_update(proposed, change)
        change_input = {**asdict(change), "live": live}
        return self._create_preview(
            vm_base,
            "interface_update",
            change_input,
            current,
            proposed,
            original_xml,
            original_hash,
        )

    def execute(
        self,
        plan_id: str,
        *,
        task_id: str,
        expected_change_type: str | None = None,
        progress: ChangeProgress | None = None,
    ) -> str:
        plan = self.plan_store.load(plan_id, VmChangePlanStatus.CONFIRMED)
        self._cached_plan = plan
        return super().execute(
            plan_id,
            task_id=task_id,
            expected_change_type=expected_change_type,
            progress=progress,
        )

    def _verified_after_hash(
        self,
        plan: VmChangePlan,
        observation: ResourceObservation,
    ) -> str:
        if plan.change_type not in {"interface_attach", "interface_detach", "interface_update"}:
            return super()._verified_after_hash(plan, observation)
        content = observation.documents.get("persistent_xml")
        if content is None or observation.persistent_hash is None:
            raise VmChangeConflict("authoritative persistent VM XML is unavailable")
        payload = _change_input(plan.change_input_json)
        if plan.change_type == "interface_attach":
            change = InterfaceAttachChange(
                str(payload.get("kind")),
                str(payload.get("source")),
                str(payload.get("model")),
                _optional_str(payload.get("mac")),
            )
            document = LibvirtXmlDocument.parse(content, expected_root="domain")
            try:
                verify_interface_attach_result(
                    document,
                    change,
                    original_hash=plan.base_persistent_hash,
                )
            except ValueError as exc:
                raise VmChangeConflict(str(exc)) from exc
            return observation.persistent_hash
        return self._verified_interface_identity(plan, observation)

    def _verified_interface_identity(
        self,
        plan: VmChangePlan,
        observation: ResourceObservation,
    ) -> str:
        content = observation.documents.get("persistent_xml")
        if content is None or observation.persistent_hash is None:
            raise VmChangeConflict("authoritative persistent VM XML is unavailable")
        document = LibvirtXmlDocument.parse(content, expected_root="domain")
        interfaces = document.root.findall("./devices/interface")
        expected_macs = self._expected_interface_macs(plan)
        actual_macs = {_interface_mac(interface) for interface in interfaces}
        if actual_macs != expected_macs:
            raise VmChangeConflict("authoritative interface set differs from the plan")
        return observation.persistent_hash

    def _expected_interface_macs(self, plan: VmChangePlan) -> set[str]:
        payload = _change_input(plan.change_input_json)
        original = LibvirtXmlDocument.parse(plan.original_xml, expected_root="domain")
        macs = {
            value
            for value in (
                _interface_mac(interface)
                for interface in original.root.findall("./devices/interface")
            )
            if value is not None
        }
        change_type = plan.change_type
        target = str(payload.get("mac") or "")
        if change_type == "interface_detach":
            macs.discard(target)
        elif change_type == "interface_update" and payload.get("new_mac"):
            new_mac = str(payload["new_mac"])
            macs.discard(target)
            macs.add(new_mac)
        return macs

    def _refresh_domains(self, host_id: str) -> None:
        self.discovery.run(host_id)

    def _define(self, host_id: str, content: bytes) -> CommandResult:
        payload = _change_input(self._current_plan.change_input_json)
        if not bool(payload.get("live", False)):
            return super()._define(host_id, content)
        return self._apply_live_device(host_id, content, payload)

    def _apply_live_device(
        self,
        host_id: str,
        full_xml: bytes,
        payload: dict[str, object],
    ) -> CommandResult:
        host = self._host(host_id)
        change_type = self._current_plan.change_type
        device_xml = _extract_interface_xml(full_xml, change_type, payload)
        args = (
            "-c",
            host.libvirt_uri,
            "attach-device",
            self._current_plan.vm_uuid,
            "/dev/stdin",
            "--live",
            "--persistent",
        )
        return self.executor.run(
            host_id,
            CommandSpec("virsh", args),
            sudo=_uses_sudo(host),
            timeout=60,
            stdin=device_xml,
            env={"LC_ALL": "C"},
            sensitive=True,
        )

    @property
    def _current_plan(self) -> VmChangePlan:
        if self._cached_plan is None:
            raise VmChangeError("no active network change plan")
        return self._cached_plan

    @_current_plan.setter
    def _current_plan(self, value: VmChangePlan) -> None:
        self._cached_plan = value


def _extract_interface_xml(
    full_xml: bytes,
    change_type: str,
    payload: dict[str, object],
) -> bytes:
    tree = etree.parse(BytesIO(full_xml))
    root = tree.getroot()
    if change_type == "interface_attach":
        kind = str(payload.get("kind"))
        source = str(payload.get("source"))
        for interface in root.findall("./devices/interface"):
            if interface.get("type") == kind and _interface_source(interface) == source:
                return etree.tostring(interface, encoding="UTF-8")
        raise VmChangeConflict("interface device not found in proposed XML")
    mac = str(payload.get("mac") or "")
    for interface in root.findall("./devices/interface"):
        if _interface_mac(interface) == mac:
            return etree.tostring(interface, encoding="UTF-8")
    raise VmChangeConflict("interface device not found in original XML")


def _interface_mac(interface: etree._Element) -> str | None:
    mac = interface.find("mac")
    value = mac.get("address") if mac is not None else None
    return value.lower() if isinstance(value, str) else None


def _interface_source(interface: etree._Element) -> str | None:
    source = interface.find("source")
    if source is None:
        return None
    for attribute in ("bridge", "network", "dev"):
        value = source.get(attribute)
        if value is not None:
            return value
    return None


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value


def _change_input(value: str) -> dict[str, object]:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise VmChangeConflict("network change input is invalid") from exc
    if not isinstance(payload, dict):
        raise VmChangeConflict("network change input is invalid")
    return payload
