"""Single-use loopback WebSocket-to-TCP proxy subprocess."""

import argparse
import asyncio

from websockets.asyncio.server import ServerConnection, serve
from websockets.typing import Subprotocol

CHUNK_SIZE = 64 * 1024


async def _proxy(websocket: ServerConnection, target_port: int) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", target_port)

    async def from_tcp() -> None:
        while data := await reader.read(CHUNK_SIZE):
            await websocket.send(data)

    async def from_websocket() -> None:
        async for data in websocket:
            if not isinstance(data, bytes):
                raise ValueError("binary WebSocket frames required")
            if len(data) > CHUNK_SIZE:
                raise ValueError("WebSocket frame exceeded limit")
            writer.write(data)
            await writer.drain()

    tasks = {asyncio.create_task(from_tcp()), asyncio.create_task(from_websocket())}
    _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    writer.close()
    await writer.wait_closed()


async def _run(target_port: int, idle_timeout: int) -> None:
    completed = asyncio.Event()

    async def handler(websocket: ServerConnection) -> None:
        try:
            await _proxy(websocket, target_port)
        finally:
            completed.set()

    async with serve(
        handler,
        "127.0.0.1",
        0,
        subprotocols=[Subprotocol("binary")],
        compression=None,
        max_size=None,
        max_queue=16,
    ) as server:
        sockets = server.sockets
        if not sockets:
            raise RuntimeError("websockify listener was not created")
        print(f"READY {sockets[0].getsockname()[1]}", flush=True)
        await asyncio.wait_for(completed.wait(), timeout=idle_timeout)


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--target-port", type=int, required=True)
    parser.add_argument("--idle-timeout", type=int, default=300)
    arguments = parser.parse_args()
    if not 1 <= arguments.target_port <= 65_535:
        raise SystemExit("invalid target port")
    if not 5 <= arguments.idle_timeout <= 3_600:
        raise SystemExit("invalid idle timeout")
    asyncio.run(_run(arguments.target_port, arguments.idle_timeout))


if __name__ == "__main__":
    main()
