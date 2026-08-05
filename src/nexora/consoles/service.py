"""VM authority checks before issuing a one-time console credential."""

from nexora.auth.sessions import SessionIdentity
from nexora.consoles.models import ConsoleKind
from nexora.consoles.store import ConsoleCredentials, ConsoleSessionStore
from nexora.consoles.vnc import VncTargetService
from nexora.db import Database
from nexora.vms.read_service import VmReadService
from nexora.xml import LibvirtXmlDocument
from nexora.xml.errors import XmlSafetyError, XmlStructureError


class ConsoleUnavailableError(RuntimeError):
    pass


class ConsoleService:
    def __init__(
        self,
        database: Database,
        store: ConsoleSessionStore,
        vnc_targets: VncTargetService | None = None,
    ) -> None:
        self.vm_read = VmReadService(database)
        self.store = store
        self.vnc_targets = vnc_targets

    def create_serial(
        self,
        identity: SessionIdentity,
        host_id: str,
        vm_uuid: str,
    ) -> ConsoleCredentials:
        detail = self.vm_read.detail(host_id, vm_uuid)
        if detail is None:
            raise ConsoleUnavailableError("虚拟机不存在")
        if not bool(detail.details.get("active")):
            raise ConsoleUnavailableError("虚拟机未运行")
        content = detail.documents.get("live_xml") or detail.documents.get("persistent_xml")
        if content is None or not _has_serial_console(content):
            raise ConsoleUnavailableError("虚拟机未配置 PTY 串口控制台")
        return self.store.create(
            identity.token_hash,
            host_id,
            detail.resource.native_id,
            ConsoleKind.SERIAL,
        )

    def create_vnc(
        self,
        identity: SessionIdentity,
        host_id: str,
        vm_uuid: str,
    ) -> ConsoleCredentials:
        if self.vnc_targets is None:
            raise ConsoleUnavailableError("VNC 控制台未启用")
        try:
            self.vnc_targets.endpoint(host_id, vm_uuid)
        except RuntimeError as exc:
            raise ConsoleUnavailableError(str(exc)) from exc
        return self.store.create(
            identity.token_hash,
            host_id,
            vm_uuid,
            ConsoleKind.VNC,
        )


def _has_serial_console(content: str) -> bool:
    try:
        document = LibvirtXmlDocument.parse(content.encode(), expected_root="domain")
    except (XmlSafetyError, XmlStructureError):
        return False
    return any(
        node.get("type") == "pty"
        for node in (
            *document.root.findall("./devices/serial"),
            *document.root.findall("./devices/console"),
        )
    )
