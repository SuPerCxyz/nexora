"""Source-IP-bound platform HTTP ISO plans for existing CD-ROM devices."""

import json
from dataclasses import asdict
from ipaddress import ip_address
from pathlib import PurePosixPath
from urllib.parse import SplitResult, urlsplit

from nexora.config import Settings
from nexora.db import Database
from nexora.hosts.models import SudoMode
from nexora.media.credentials import MediaCredentialService
from nexora.media.models import MediaItem, MediaKind, MediaStatus
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.conflicts import ResourceBaseVersion, ResourceWriteGuard
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.tasks.locks import ResourceLockStore
from nexora.vms.cdrom_changes import VmCdromChangeService
from nexora.vms.change_models import VmChangePlanStatus
from nexora.vms.cpu_changes import ChangeProgress, VmChangeConflict, VmChangePreview
from nexora.xml import (
    CdromHttpChange,
    CdromMediaChange,
    LibvirtXmlDocument,
    apply_cdrom_http,
    apply_cdrom_media,
)


class VmPlatformIsoService(VmCdromChangeService):
    def __init__(
        self,
        settings: Settings,
        database: Database,
        executor: RemoteExecutor,
        discovery: DomainDiscoveryService,
        store: ResourceIndexStore,
        guard: ResourceWriteGuard,
        locks: ResourceLockStore,
        storage_discovery: StorageDiscoveryService,
        credentials: MediaCredentialService,
    ) -> None:
        super().__init__(
            database,
            executor,
            discovery,
            store,
            guard,
            locks,
            storage_discovery,
        )
        self.settings = settings
        self.credentials = credentials

    def preview_platform_mount(
        self,
        vm_base: ResourceBaseVersion,
        media_item_id: str,
        *,
        target: str,
        bus: str,
        expected_source: str | None,
    ) -> VmChangePreview:
        origin = self._origin()
        self._require_ip_host(vm_base.host_id)
        self._require_inactive(vm_base.host_id, vm_base.native_id)
        item = self._media_item(media_item_id)
        current, original_xml, original_hash = self._current_persistent(vm_base)
        credential = self.credentials.issue_for_node(
            item.id,
            host_id=vm_base.host_id,
            vm_uuid=vm_base.native_id,
        )
        path = f"/media/content/{credential.id}"
        change = CdromHttpChange(
            target,
            bus,
            expected_source,
            origin.scheme,
            str(origin.hostname),
            origin.port or (443 if origin.scheme == "https" else 80),
            path,
            credential.id,
        )
        try:
            self._probe_http(vm_base.host_id, origin, path)
            proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
            apply_cdrom_http(proposed, change)
            return self._create_preview(
                vm_base,
                "cdrom_platform_mount",
                {
                    **asdict(change),
                    "media_item_id": item.id,
                    "media_sha256": item.sha256,
                },
                current,
                proposed,
                original_xml,
                original_hash,
            )
        except Exception:
            self.credentials.revoke(credential.id)
            raise

    def preview_platform_eject(
        self,
        vm_base: ResourceBaseVersion,
        *,
        target: str,
        bus: str,
        expected_source: str,
    ) -> VmChangePreview:
        self._require_inactive(vm_base.host_id, vm_base.native_id)
        credential_id = _credential_id(expected_source)
        current, original_xml, original_hash = self._current_persistent(vm_base)
        change = CdromMediaChange(target, bus, expected_source, None)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_cdrom_media(proposed, change)
        return self._create_preview(
            vm_base,
            "cdrom_platform_eject",
            {**asdict(change), "credential_id": credential_id},
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
        self._require_inactive(plan.host_id, plan.vm_uuid)
        payload = _payload(plan.change_input_json)
        credential_id = str(payload["credential_id"])
        if plan.change_type == "cdrom_platform_mount":
            host_address = self._require_ip_host(plan.host_id)
            try:
                item = self.credentials.authenticate_node(credential_id, host_address)
                if item.id != payload.get("media_item_id") or item.sha256 != payload.get(
                    "media_sha256"
                ):
                    raise VmChangeConflict("platform ISO changed after preview")
                return super().execute(
                    plan_id,
                    task_id=task_id,
                    expected_change_type=expected_change_type,
                    progress=progress,
                )
            except Exception:
                self.credentials.revoke(credential_id)
                raise
        result = super().execute(
            plan_id,
            task_id=task_id,
            expected_change_type=expected_change_type,
            progress=progress,
        )
        self.credentials.revoke(credential_id)
        return result

    def _origin(self) -> SplitResult:
        value = self.settings.media_public_base_url
        if value is None:
            raise VmChangeConflict("platform media public URL is not configured")
        return urlsplit(value)

    def _require_ip_host(self, host_id: str) -> str:
        host = self._host(host_id)
        try:
            return str(ip_address(host.address))
        except ValueError as exc:
            raise VmChangeConflict(
                "platform ISO source binding currently requires a host IP address"
            ) from exc

    def _media_item(self, item_id: str) -> MediaItem:
        with self.database.session() as session:
            item = session.get(MediaItem, item_id)
            if item is None or item.kind != MediaKind.ISO or item.status != MediaStatus.AVAILABLE:
                raise VmChangeConflict("platform ISO is unavailable")
            return item

    def _require_inactive(self, host_id: str, vm_uuid: str) -> None:
        observation = self.discovery.read_one(host_id, vm_uuid)
        if bool(observation.details.get("active")):
            raise VmChangeConflict(
                "platform ISO changes require a shut-off VM to preserve media access"
            )

    def _probe_http(self, host_id: str, origin: SplitResult, path: str) -> None:
        url = origin._replace(path=path, query="", fragment="").geturl()
        host = self._host(host_id)
        sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        capabilities = self.executor.run(
            host_id,
            CommandSpec("virsh", ("-c", host.libvirt_uri, "domcapabilities")),
            sudo=sudo,
            timeout=60,
            env={"LC_ALL": "C"},
        )
        if not _successful(capabilities):
            raise VmChangeConflict("node QEMU emulator discovery failed")
        document = LibvirtXmlDocument.parse(
            capabilities.stdout,
            expected_root="domainCapabilities",
        )
        emulator = _emulator_path(document.root.findtext("path"))
        result = self.executor.run(
            host_id,
            CommandSpec(
                "env",
                (
                    "--",
                    emulator,
                    "-machine",
                    "none",
                    "-nodefaults",
                    "-display",
                    "none",
                    "-blockdev",
                    f"driver=http,url={url},node-name=nexora_probe",
                    "-qmp",
                    "stdio",
                ),
            ),
            sudo=sudo,
            timeout=60,
            stdin=b'{"execute":"qmp_capabilities"}\n{"execute":"quit"}\n',
            env={"LC_ALL": "C"},
            sensitive=True,
        )
        if not _successful(result):
            raise VmChangeConflict(
                "node QEMU cannot read the platform HTTP ISO; use verified cache fallback"
            )


def _credential_id(source: str) -> str:
    prefix = "/media/content/"
    if not source.startswith(prefix):
        raise VmChangeConflict("CD-ROM is not backed by a Nexora platform credential")
    value = source.removeprefix(prefix)
    if "/" in value or not value:
        raise VmChangeConflict("platform media credential identity is invalid")
    return value


def _payload(value: str) -> dict[str, object]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise VmChangeConflict("platform ISO change input is invalid") from exc
    if not isinstance(payload, dict) or "credential_id" not in payload:
        raise VmChangeConflict("platform ISO change input is invalid")
    return payload


def _emulator_path(value: str | None) -> str:
    if value is None or "\0" in value:
        raise VmChangeConflict("node QEMU emulator path is unavailable")
    path = PurePosixPath(value)
    allowed_parent = any(
        path.is_relative_to(root)
        for root in (
            PurePosixPath("/usr/bin"),
            PurePosixPath("/usr/lib"),
            PurePosixPath("/usr/libexec"),
        )
    )
    if (
        not path.is_absolute()
        or ".." in path.parts
        or not allowed_parent
        or (path.name != "qemu-kvm" and not path.name.startswith("qemu-system-"))
    ):
        raise VmChangeConflict("node QEMU emulator path is unsafe")
    return str(path)


def _successful(result: CommandResult) -> bool:
    return not (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    )
