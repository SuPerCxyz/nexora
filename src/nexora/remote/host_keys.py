"""SSH Host Key value objects and comparison."""

import base64
import binascii
import hashlib
from dataclasses import dataclass
from enum import StrEnum

ALLOWED_KEY_TYPES = {
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
}


class HostKeyStatus(StrEnum):
    NEW = "new"
    MATCH = "match"
    CHANGED = "changed"


@dataclass(frozen=True)
class HostKeyCandidate:
    """A discovered public Host Key awaiting trust confirmation."""

    host: str
    port: int
    key_type: str
    key_data: str

    def __post_init__(self) -> None:
        if self.key_type not in ALLOWED_KEY_TYPES:
            raise ValueError("unsupported Host Key type")
        try:
            base64.b64decode(self.key_data, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("invalid Host Key data") from None

    @property
    def fingerprint(self) -> str:
        key = base64.b64decode(self.key_data, validate=True)
        digest = base64.b64encode(hashlib.sha256(key).digest()).decode().rstrip("=")
        return f"SHA256:{digest}"

    @property
    def known_hosts_line(self) -> str:
        marker = self.host if self.port == 22 else f"[{self.host}]:{self.port}"
        return f"{marker} {self.key_type} {self.key_data}"

    @property
    def identity(self) -> tuple[str, str]:
        return self.key_type, self.key_data


def compare_host_keys(
    discovered: list[HostKeyCandidate],
    trusted: list[HostKeyCandidate],
) -> HostKeyStatus:
    if not trusted:
        return HostKeyStatus.NEW
    discovered_identities = {key.identity for key in discovered}
    trusted_identities = {key.identity for key in trusted}
    if discovered_identities == trusted_identities:
        return HostKeyStatus.MATCH
    return HostKeyStatus.CHANGED
