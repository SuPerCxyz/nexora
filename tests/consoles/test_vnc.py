import asyncio
import sys

import websockets
from websockets.typing import Subprotocol

from nexora.consoles.vnc import VncUnavailableError, parse_vnc_endpoint


def test_vnc_endpoint_accepts_only_loopback_display_or_port() -> None:
    assert 5_900 == parse_vnc_endpoint("vnc://127.0.0.1:0")
    assert 5_905 == parse_vnc_endpoint("vnc://localhost:5")
    assert 6_100 == parse_vnc_endpoint("vnc://[::1]:6100")
    for value in (
        "vnc://192.0.2.10:0",
        "spice://127.0.0.1:0",
        "vnc://127.0.0.1",
        "vnc://127.0.0.1:70000",
    ):
        try:
            parse_vnc_endpoint(value)
        except VncUnavailableError:
            pass
        else:
            raise AssertionError(f"unsafe VNC endpoint accepted: {value}")


def test_single_use_websockify_worker_proxies_binary_tcp() -> None:
    asyncio.run(_worker_round_trip())


async def _worker_round_trip() -> None:
    async def echo(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        writer.write(await reader.read(64 * 1024))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    target = await asyncio.start_server(echo, "127.0.0.1", 0)
    sockets = target.sockets
    assert sockets
    target_port = sockets[0].getsockname()[1]
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "nexora.consoles.websockify_worker",
        "--target-port",
        str(target_port),
        "--idle-timeout",
        "10",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        assert process.stdout is not None
        ready = await asyncio.wait_for(process.stdout.readline(), timeout=3)
        proxy_port = int(ready.decode().split()[1])
        async with websockets.connect(
            f"ws://127.0.0.1:{proxy_port}",
            subprotocols=[Subprotocol("binary")],
            compression=None,
        ) as websocket:
            await websocket.send(b"rfb-payload")
            assert b"rfb-payload" == await websocket.recv()
        assert 0 == await asyncio.wait_for(process.wait(), timeout=3)
    finally:
        target.close()
        await target.wait_closed()
        if process.returncode is None:
            process.terminate()
            await process.wait()
