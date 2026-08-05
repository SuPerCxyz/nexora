"""Audited remote commands used by VM creation."""

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.xml import LibvirtXmlDocument


class VmCreationRemote:
    def __init__(self, database: Database, executor: RemoteExecutor) -> None:
        self.database = database
        self.executor = executor

    def architecture(self, host_id: str) -> str:
        host = self._host(host_id)
        result = self.executor.run(
            host_id,
            CommandSpec("virsh", ("-c", host.libvirt_uri, "domcapabilities")),
            sudo=_uses_sudo(host),
            timeout=30,
            env={"LC_ALL": "C"},
        )
        _require_success(result, "cannot read libvirt domain capabilities")
        document = LibvirtXmlDocument.parse(result.stdout, expected_root="domainCapabilities")
        arch = document.root.findtext("arch")
        if arch not in {"x86_64", "aarch64"}:
            raise ValueError("host architecture is not supported for VM creation")
        return arch

    def validate_xml(self, host_id: str, content: bytes) -> None:
        result = self.executor.run(
            host_id,
            CommandSpec("virt-xml-validate", ("-", "domain")),
            sudo=_uses_sudo(self._host(host_id)),
            timeout=30,
            stdin=content,
            env={"LC_ALL": "C"},
            sensitive=True,
        )
        _require_success(result, "proposed VM XML failed schema validation")

    def define(self, host_id: str, content: bytes) -> None:
        host = self._host(host_id)
        result = self.executor.run(
            host_id,
            CommandSpec("virsh", ("-c", host.libvirt_uri, "define", "/dev/stdin", "--validate")),
            sudo=_uses_sudo(host),
            timeout=60,
            stdin=content,
            env={"LC_ALL": "C"},
            sensitive=True,
        )
        _require_success(result, "libvirt rejected proposed VM XML")

    def refresh_pool(self, host_id: str, pool_uuid: str) -> None:
        host = self._host(host_id)
        result = self.executor.run(
            host_id,
            CommandSpec("virsh", ("-c", host.libvirt_uri, "pool-refresh", pool_uuid)),
            sudo=_uses_sudo(host),
            timeout=60,
            env={"LC_ALL": "C"},
        )
        _require_success(result, "cannot refresh target storage pool")

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise ValueError("host not found")
            return host


def _uses_sudo(host: Host) -> bool:
    return host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS


def _require_success(result: CommandResult, message: str) -> None:
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    ):
        raise ValueError(message)
