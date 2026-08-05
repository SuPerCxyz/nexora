"""Authenticated console WebSocket bridge (serial and VNC)."""

import asyncio
import time
from urllib.parse import urlsplit

import asyncssh
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from websockets.typing import Subprotocol

from nexora.auth.sessions import SessionIdentity, SessionService
from nexora.consoles.models import ConsoleKind, ConsoleStatus
from nexora.consoles.serial import SerialConsoleConnection, SerialConsoleConnector
from nexora.consoles.store import ConsoleSessionStore
from nexora.consoles.vnc import VncProxyManager
from nexora.web.security import SESSION_COOKIE

router = APIRouter(include_in_schema=False)
PROTOCOL = "nexora.console"
VNC_PROTOCOL = "binary"
TOKEN_PREFIX = "nexora.token."
MAX_FRAME = 64 * 1024
IDLE_SECONDS = 300
HARD_SECONDS = 3_600


@router.websocket("/ws/consoles/{console_id}")
async def serial_console_socket(websocket: WebSocket, console_id: str) -> None:
    identity = _identity(
        websocket.app.state.session_service,
        websocket.cookies.get(SESSION_COOKIE),
    )
    protocol, token = _protocol_and_token(websocket)
    if identity is None or protocol is None or token is None or not _origin_matches(websocket):
        await websocket.close(code=4403)
        return
    store: ConsoleSessionStore = websocket.app.state.console_session_store
    claimed = await run_in_threadpool(store.claim, console_id, token, identity.token_hash)
    if claimed is None or (
        (claimed.kind == ConsoleKind.SERIAL and protocol != PROTOCOL)
        or (claimed.kind == ConsoleKind.VNC and protocol != VNC_PROTOCOL)
    ):
        await websocket.close(code=4403)
        return
    await websocket.accept(subprotocol=protocol)
    final_status = ConsoleStatus.CLOSED
    try:
        if claimed.kind == ConsoleKind.SERIAL:
            connector: SerialConsoleConnector = websocket.app.state.serial_console_connector
            async with connector.open(claimed.host_id, claimed.vm_uuid) as connection:
                await _bridge(websocket, connection)
        else:
            manager: VncProxyManager = websocket.app.state.vnc_proxy_manager
            async with (
                manager.open(claimed.host_id, claimed.vm_uuid) as proxy,
                websockets.connect(
                    proxy.websocket_uri,
                    subprotocols=[Subprotocol(VNC_PROTOCOL)],
                    compression=None,
                    max_size=None,
                ) as internal,
            ):
                await _vnc_bridge(websocket, internal)
    except WebSocketDisconnect:
        pass
    except (OSError, asyncssh.Error, RuntimeError, ValueError):
        final_status = ConsoleStatus.INTERRUPTED
        await websocket.close(code=1011)
    finally:
        await run_in_threadpool(store.close, console_id, status=final_status)


async def _bridge(websocket: WebSocket, connection: SerialConsoleConnection) -> None:
    activity = [time.monotonic()]

    async def from_remote() -> None:
        while data := await connection.read():
            activity[0] = time.monotonic()
            await websocket.send_bytes(data)

    async def from_browser() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            data = message.get("bytes")
            if data is None and message.get("text") is not None:
                data = str(message["text"]).encode()
            if data is None:
                continue
            if len(data) > MAX_FRAME:
                raise RuntimeError("console frame exceeded limit")
            activity[0] = time.monotonic()
            connection.write(data)

    async def watchdog() -> None:
        started = time.monotonic()
        while True:
            await asyncio.sleep(1)
            now = time.monotonic()
            if now - activity[0] > IDLE_SECONDS or now - started > HARD_SECONDS:
                raise RuntimeError("console session timed out")

    tasks = {
        asyncio.create_task(from_remote()),
        asyncio.create_task(from_browser()),
        asyncio.create_task(watchdog()),
    }
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        task.result()


async def _vnc_bridge(
    websocket: WebSocket,
    internal: websockets.ClientConnection,
) -> None:
    async def from_proxy() -> None:
        async for data in internal:
            if not isinstance(data, bytes) or len(data) > MAX_FRAME:
                raise RuntimeError("invalid websockify frame")
            await websocket.send_bytes(data)

    async def from_browser() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            data = message.get("bytes")
            if data is None or len(data) > MAX_FRAME:
                raise RuntimeError("binary VNC frame required")
            await internal.send(data)

    tasks = {asyncio.create_task(from_proxy()), asyncio.create_task(from_browser())}
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        task.result()


def _identity(service: SessionService, token: str | None) -> SessionIdentity | None:
    return service.resolve(token)


def _protocol_and_token(websocket: WebSocket) -> tuple[str | None, str | None]:
    protocols = [
        item.strip() for item in websocket.headers.get("sec-websocket-protocol", "").split(",")
    ]
    selected = (
        PROTOCOL if PROTOCOL in protocols else VNC_PROTOCOL if VNC_PROTOCOL in protocols else None
    )
    values = [
        item.removeprefix(TOKEN_PREFIX) for item in protocols if item.startswith(TOKEN_PREFIX)
    ]
    token = values[0] if len(values) == 1 and 1 <= len(values[0]) <= 128 else None
    return selected, token


def _origin_matches(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host")
    if origin is None or host is None:
        return False
    parsed = urlsplit(origin)
    return parsed.scheme in {"http", "https"} and parsed.netloc == host
