import sys
from threading import Event

from nexora.remote.process import BoundedProcessRunner


def test_process_separates_output_and_stdin() -> None:
    runner = BoundedProcessRunner()

    result = runner.run(
        [
            sys.executable,
            "-c",
            "import sys; data=sys.stdin.buffer.read(); "
            "sys.stdout.buffer.write(data); sys.stderr.write('warning')",
        ],
        timeout=5,
        stdin=b"input",
    )

    assert 0 == result.exit_code
    assert b"input" == result.stdout
    assert b"warning" == result.stderr
    assert result.timed_out is False
    assert result.cancelled is False


def test_process_output_is_bounded_per_stream() -> None:
    runner = BoundedProcessRunner(max_output_bytes=16)

    result = runner.run(
        [
            sys.executable,
            "-c",
            "import sys; print('x'*100); print('y'*100, file=sys.stderr)",
        ],
        timeout=5,
    )

    assert 16 == len(result.stdout)
    assert 16 == len(result.stderr)
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True


def test_process_timeout_terminates_process_group() -> None:
    runner = BoundedProcessRunner()

    result = runner.run(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout=1,
    )

    assert result.timed_out is True
    assert result.duration_seconds < 5
    assert result.exit_code != 0


def test_process_honors_pre_requested_cancellation() -> None:
    runner = BoundedProcessRunner()
    cancellation = Event()
    cancellation.set()

    result = runner.run(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout=10,
        cancel_event=cancellation,
    )

    assert result.cancelled is True
    assert result.duration_seconds < 5
