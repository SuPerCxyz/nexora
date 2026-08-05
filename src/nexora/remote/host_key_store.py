"""Confirmed SSH Host Key persistence."""

import os
import tempfile
from pathlib import Path

from nexora.remote.host_keys import HostKeyCandidate
from nexora.remote.validation import validate_resource_id


class HostKeyStore:
    """Persist one strict known_hosts file per managed host."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    def path_for(self, host_id: str) -> Path:
        return self.directory / f"{validate_resource_id(host_id)}.known_hosts"

    def delete(self, host_id: str) -> None:
        self.path_for(host_id).unlink(missing_ok=True)

    def save(self, host_id: str, candidates: list[HostKeyCandidate]) -> Path:
        if not candidates:
            raise ValueError("at least one Host Key is required")
        target = self.path_for(host_id)
        content = "".join(f"{candidate.known_hosts_line}\n" for candidate in candidates)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.directory,
            prefix=".nexora-hostkey-",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return target

    def load(
        self,
        host_id: str,
        *,
        host: str,
        port: int,
    ) -> list[HostKeyCandidate]:
        path = self.path_for(host_id)
        if not path.exists():
            return []
        candidates: list[HostKeyCandidate] = []
        for line in path.read_text(encoding="ascii").splitlines():
            parts = line.split()
            if len(parts) != 3:
                raise ValueError("stored Host Key file is malformed")
            _, key_type, key_data = parts
            candidates.append(HostKeyCandidate(host, port, key_type, key_data))
        return candidates
