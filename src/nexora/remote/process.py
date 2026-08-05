"""Bounded subprocess execution for SSH clients."""

import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from threading import Event
from typing import BinaryIO, cast

READ_SIZE = 64 * 1024
MAX_STDIN_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool
    cancelled: bool
    duration_seconds: float


class BoundedProcessRunner:
    """Run a process without allowing unbounded pipe memory."""

    def __init__(self, *, max_output_bytes: int = 4 * 1024 * 1024) -> None:
        if not 1 <= max_output_bytes <= 64 * 1024 * 1024:
            raise ValueError("invalid output limit")
        self.max_output_bytes = max_output_bytes

    def run(
        self,
        argv: list[str],
        *,
        timeout: int,
        stdin: bytes | None = None,
        cancel_event: Event | None = None,
    ) -> ProcessResult:
        if not 1 <= timeout <= 86_400:
            raise ValueError("invalid command timeout")
        if stdin is not None and len(stdin) > MAX_STDIN_BYTES:
            raise ValueError("stdin exceeded limit")
        started = time.monotonic()
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        return _collect_process(
            process,
            stdin=stdin,
            output_limit=self.max_output_bytes,
            deadline=started + timeout,
            started=started,
            cancel_event=cancel_event,
        )


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)


def _collect_process(
    process: subprocess.Popen[bytes],
    *,
    stdin: bytes | None,
    output_limit: int,
    deadline: float,
    started: float,
    cancel_event: Event | None,
) -> ProcessResult:
    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    assert process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    stdin_offset = 0
    if stdin is not None:
        assert process.stdin is not None
        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")

    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    truncated = {"stdout": False, "stderr": False}
    timed_out = False
    cancelled = False
    terminated = False

    while selector.get_map():
        now = time.monotonic()
        if not terminated and cancel_event is not None and cancel_event.is_set():
            cancelled = True
            terminated = True
            _terminate(process)
        elif not terminated and now >= deadline:
            timed_out = True
            terminated = True
            _terminate(process)

        for key, _mask in selector.select(0.1):
            stream = cast(BinaryIO, key.fileobj)
            channel = key.data
            if channel == "stdin":
                assert stdin is not None
                try:
                    written = os.write(stream.fileno(), stdin[stdin_offset:])
                    stdin_offset += written
                except BrokenPipeError:
                    stdin_offset = len(stdin)
                if stdin_offset >= len(stdin):
                    selector.unregister(stream)
                    stream.close()
                continue

            chunk = os.read(stream.fileno(), READ_SIZE)
            if not chunk:
                selector.unregister(stream)
                stream.close()
                continue
            buffer = buffers[channel]
            remaining = output_limit - len(buffer)
            if remaining > 0:
                buffer.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated[channel] = True

    exit_code = process.wait()
    return ProcessResult(
        exit_code=exit_code,
        stdout=bytes(buffers["stdout"]),
        stderr=bytes(buffers["stderr"]),
        stdout_truncated=truncated["stdout"],
        stderr_truncated=truncated["stderr"],
        timed_out=timed_out,
        cancelled=cancelled,
        duration_seconds=time.monotonic() - started,
    )
