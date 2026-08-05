"""Bounded read-only QEMU Guest Agent status collection."""

import ipaddress
import json
from dataclasses import dataclass

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.vms.read_service import VmReadService
from nexora.xml import LibvirtXmlDocument
from nexora.xml.errors import XmlSafetyError, XmlStructureError

MAX_AGENT_OUTPUT = 1024 * 1024
MAX_INTERFACES = 256
MAX_ADDRESSES_PER_INTERFACE = 64
AGENT_TARGET = "org.qemu.guest_agent.0"


@dataclass(frozen=True)
class GuestAddress:
    interface: str
    address: str
    prefix: int
    family: str
    mac: str | None


@dataclass(frozen=True)
class GuestAgentView:
    state: str
    channel_configured: bool
    hostname: str | None = None
    addresses: tuple[GuestAddress, ...] = ()
    message: str | None = None


class GuestAgentService:
    def __init__(self, database: Database, executor: RemoteExecutor) -> None:
        self.database = database
        self.executor = executor

    def read(self, host_id: str, vm_uuid: str) -> GuestAgentView:
        detail = VmReadService(self.database).detail(host_id, vm_uuid)
        if detail is None:
            raise ValueError("virtual machine not found")
        configured = _channel_configured(detail.documents)
        if not configured:
            return GuestAgentView(
                "not_configured",
                False,
                message="未配置 QEMU Guest Agent Channel",
            )
        if str(detail.details.get("state", "")).lower() != "running":
            return GuestAgentView("stopped", True, message="虚拟机未运行")
        if self._command(detail.host, vm_uuid, "guest-ping") is None:
            return GuestAgentView(
                "unavailable",
                True,
                message="Guest Agent 未安装、未启动或暂未响应",
            )
        hostname = _hostname(self._command(detail.host, vm_uuid, "guest-get-host-name"))
        addresses = _addresses(self._command(detail.host, vm_uuid, "guest-network-get-interfaces"))
        return GuestAgentView("connected", True, hostname, addresses)

    def _command(
        self,
        host: Host,
        vm_uuid: str,
        execute: str,
    ) -> object | None:
        payload = json.dumps({"execute": execute}, separators=(",", ":"))
        result = self.executor.run(
            host.id,
            CommandSpec(
                "virsh",
                (
                    "-c",
                    host.libvirt_uri,
                    "qemu-agent-command",
                    vm_uuid,
                    payload,
                    "--timeout",
                    "5",
                ),
            ),
            sudo=host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS,
            timeout=10,
            env={"LC_ALL": "C"},
            sensitive=True,
        )
        if not _success(result):
            return None
        try:
            parsed: object = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict) or "error" in parsed or "return" not in parsed:
            return None
        value: object = parsed["return"]
        return value


def _channel_configured(documents: dict[str, str]) -> bool:
    content = documents.get("live_xml") or documents.get("persistent_xml")
    if content is None:
        return False
    try:
        document = LibvirtXmlDocument.parse(content.encode(), expected_root="domain")
    except (XmlSafetyError, XmlStructureError):
        return False
    return any(
        target.get("name") == AGENT_TARGET
        for target in document.root.findall("./devices/channel/target")
    )


def _success(result: CommandResult) -> bool:
    return (
        result.exit_code == 0
        and not result.timed_out
        and not result.cancelled
        and not result.stdout_truncated
        and not result.stderr_truncated
        and len(result.stdout) <= MAX_AGENT_OUTPUT
    )


def _hostname(value: object | None) -> str | None:
    if not isinstance(value, dict):
        return None
    hostname = value.get("host-name")
    if (
        not isinstance(hostname, str)
        or not 1 <= len(hostname) <= 253
        or any(ord(character) < 32 for character in hostname)
    ):
        return None
    return hostname


def _addresses(value: object | None) -> tuple[GuestAddress, ...]:
    if not isinstance(value, list) or len(value) > MAX_INTERFACES:
        return ()
    results: list[GuestAddress] = []
    for interface in value:
        if not isinstance(interface, dict):
            continue
        name = _short_text(interface.get("name"), 128)
        mac = _mac(interface.get("hardware-address"))
        entries = interface.get("ip-addresses")
        if (
            name is None
            or not isinstance(entries, list)
            or len(entries) > MAX_ADDRESSES_PER_INTERFACE
        ):
            continue
        for entry in entries:
            parsed = _address(name, mac, entry)
            if parsed is not None:
                results.append(parsed)
    return tuple(results)


def _address(interface: str, mac: str | None, value: object) -> GuestAddress | None:
    if not isinstance(value, dict):
        return None
    text = value.get("ip-address")
    prefix = value.get("prefix")
    if not isinstance(text, str) or not isinstance(prefix, int) or isinstance(prefix, bool):
        return None
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        return None
    maximum = 32 if address.version == 4 else 128
    if not 0 <= prefix <= maximum:
        return None
    return GuestAddress(interface, str(address), prefix, f"IPv{address.version}", mac)


def _short_text(value: object, limit: int) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        return None
    if any(ord(character) < 32 for character in value):
        return None
    return value


def _mac(value: object) -> str | None:
    text = _short_text(value, 17)
    if text is None:
        return None
    try:
        parts = [int(part, 16) for part in text.split(":")]
    except ValueError:
        return None
    return text.lower() if len(parts) == 6 and all(0 <= part <= 255 for part in parts) else None
