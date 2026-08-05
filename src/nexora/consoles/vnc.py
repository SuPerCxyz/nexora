"""VNC authority discovery and per-session SSH/websockify lifecycle."""

import asyncio
import os
import signal
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

import asyncssh

from nexora.db import Database
from nexora.hosts.models import SudoMode
from nexora.remote.async_ssh_backend import asyncssh_connection_options
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import ConnectionResolver, RemoteExecutor
from nexora.vms.read_service import VmReadService
from nexora.xml import LibvirtXmlDocument
from nexora.xml.errors import XmlSafetyError, XmlStructureError


class VncUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class VncProxy:
    websocket_uri: str


class VncTargetService:
    def __init__(self, database: Database, executor: RemoteExecutor) -> None:
        self.database = database
        self.executor = executor
        self.vm_read = VmReadService(database)

    def endpoint(self, host_id: str, vm_uuid: str) -> int:
        detail = self.vm_read.detail(host_id, vm_uuid)
        if detail is None or not bool(detail.details.get("active")):
            raise VncUnavailableError("虚拟机未运行")
        content = detail.documents.get("live_xml")
        if content is None:
            raise VncUnavailableError("缺少运行时虚拟机 XML")
        _validate_vnc_graphics(content)
        host = detail.host
        result = self.executor.run(
            host_id,
            CommandSpec(
                "virsh",
                ("-c", host.libvirt_uri, "domdisplay", str(UUID(vm_uuid)), "--type", "vnc"),
            ),
            sudo=host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS,
            timeout=10,
            env={"LC_ALL": "C"},
            sensitive=True,
        )
        if result.exit_code != 0 or result.timed_out or result.stdout_truncated:
            raise VncUnavailableError("无法读取 VNC endpoint")
        return parse_vnc_endpoint(result.stdout.decode(errors="strict").strip())


class VncProxyManager:
    def __init__(
        self,
        database: Database,
        resolver: ConnectionResolver,
        targets: VncTargetService,
    ) -> None:
        self.database = database
        self.resolver = resolver
        self.targets = targets
        self.processes: set[asyncio.subprocess.Process] = set()

    @asynccontextmanager
    async def open(self, host_id: str, vm_uuid: str) -> AsyncIterator[VncProxy]:
        remote_port = await asyncio.to_thread(self.targets.endpoint, host_id, vm_uuid)
        profile = await asyncio.to_thread(self.resolver.resolve, host_id)
        connection = await asyncssh.connect(
            profile.connection.host,
            port=profile.connection.port,
            username=profile.connection.username,
            known_hosts=str(profile.connection.known_hosts_file),
            config=None,
            agent_path=None,
            connect_timeout=15,
            login_timeout=15,
            **asyncssh_connection_options(profile),
        )
        listener = await connection.forward_local_port(
            "127.0.0.1",
            0,
            "127.0.0.1",
            remote_port,
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "nexora.consoles.websockify_worker",
            "--target-port",
            str(listener.get_port()),
            "--idle-timeout",
            "300",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        self.processes.add(process)
        try:
            if process.stdout is None:
                raise RuntimeError("websockify stdout unavailable")
            ready = await asyncio.wait_for(process.stdout.readline(), timeout=5)
            parts = ready.decode().strip().split()
            if len(parts) != 2 or parts[0] != "READY":
                raise RuntimeError("websockify failed to become ready")
            port = int(parts[1])
            if not 1 <= port <= 65_535:
                raise RuntimeError("websockify returned invalid port")
            yield VncProxy(f"ws://127.0.0.1:{port}")
        finally:
            await _stop_process(process)
            self.processes.discard(process)
            listener.close()
            await listener.wait_closed()
            connection.close()
            await connection.wait_closed()

    async def close_all(self) -> None:
        await asyncio.gather(*(_stop_process(item) for item in tuple(self.processes)))
        self.processes.clear()


def parse_vnc_endpoint(value: str) -> int:
    parsed = urlsplit(value)
    if parsed.scheme != "vnc" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise VncUnavailableError("VNC endpoint 不是远端回环地址")
    try:
        value_port = parsed.port
    except ValueError as exc:
        raise VncUnavailableError("VNC endpoint 端口无效") from exc
    if value_port is None:
        raise VncUnavailableError("VNC endpoint 缺少端口")
    port = 5_900 + value_port if value_port < 100 else value_port
    if not 5_900 <= port <= 65_535:
        raise VncUnavailableError("VNC endpoint 端口超出范围")
    return port


def _validate_vnc_graphics(content: str) -> None:
    try:
        document = LibvirtXmlDocument.parse(content.encode(), expected_root="domain")
    except (XmlSafetyError, XmlStructureError) as exc:
        raise VncUnavailableError("运行时 XML 不可用") from exc
    nodes = document.root.findall("./devices/graphics[@type='vnc']")
    if len(nodes) != 1:
        raise VncUnavailableError("虚拟机未配置唯一 VNC graphics")
    if nodes[0].get("socket"):
        raise VncUnavailableError("Unix socket VNC 暂不支持")
    if nodes[0].get("passwd"):
        raise VncUnavailableError("首期不代理带密码的 VNC")


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        await process.wait()
