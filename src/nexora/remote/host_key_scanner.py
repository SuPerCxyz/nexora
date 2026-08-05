"""Read-only SSH Host Key discovery."""

import subprocess

from nexora.remote.host_keys import HostKeyCandidate
from nexora.remote.validation import validate_host, validate_port


class HostKeyScanError(RuntimeError):
    """Raised when discovery cannot produce a valid Host Key."""


def scan_host_keys(host: str, port: int, *, timeout: int = 10) -> list[HostKeyCandidate]:
    normalized_host = validate_host(host)
    normalized_port = validate_port(port)
    if not 1 <= timeout <= 60:
        raise ValueError("invalid scan timeout")
    try:
        result = subprocess.run(
            [
                "ssh-keyscan",
                "-T",
                str(timeout),
                "-p",
                str(normalized_port),
                normalized_host,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HostKeyScanError("SSH Host Key scan failed") from exc
    if len(result.stdout) > 256 * 1024:
        raise HostKeyScanError("SSH Host Key scan output exceeded limit")

    candidates: list[HostKeyCandidate] = []
    for line in result.stdout.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3:
            continue
        _, key_type, key_data = parts
        try:
            candidate = HostKeyCandidate(
                normalized_host,
                normalized_port,
                key_type,
                key_data,
            )
        except ValueError:
            continue
        if candidate not in candidates:
            candidates.append(candidate)
    if not candidates:
        raise HostKeyScanError("SSH Host Key scan returned no supported keys")
    return candidates
