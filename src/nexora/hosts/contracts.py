"""Validated host onboarding inputs and secret payloads."""

import json
import re
from dataclasses import dataclass

import asyncssh

from nexora.hosts.models import AuthenticationMethod, SudoMode
from nexora.remote.ssh import USERNAME_PATTERN
from nexora.remote.validation import validate_host, validate_port

LABEL_PATTERN = re.compile(r"^[\w.:-]{1,64}$")


@dataclass(frozen=True)
class CredentialPayload:
    password: str | None = None
    private_key: str | None = None
    private_key_passphrase: str | None = None

    def validate(self, method: AuthenticationMethod) -> None:
        if method == AuthenticationMethod.PASSWORD:
            if not self.password or self.private_key or self.private_key_passphrase:
                raise ValueError("password authentication requires only a password")
            if len(self.password) > 4_096:
                raise ValueError("password exceeds size limit")
            return
        if not self.private_key or self.password:
            raise ValueError("private key authentication requires a private key")
        if len(self.private_key.encode()) > 1024 * 1024:
            raise ValueError("private key exceeds size limit")
        if self.private_key_passphrase is not None and len(self.private_key_passphrase) > 4_096:
            raise ValueError("private key passphrase exceeds size limit")
        try:
            asyncssh.import_private_key(
                self.private_key,
                passphrase=self.private_key_passphrase,
            )
        except asyncssh.KeyImportError:
            raise ValueError("private key format is not recognized") from None

    def encode(self) -> bytes:
        return json.dumps(
            {
                "password": self.password,
                "private_key": self.private_key,
                "private_key_passphrase": self.private_key_passphrase,
            },
            separators=(",", ":"),
        ).encode()

    @classmethod
    def decode(cls, value: bytes) -> "CredentialPayload":
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("credential payload is malformed")
        allowed = {"password", "private_key", "private_key_passphrase"}
        if set(parsed) != allowed:
            raise ValueError("credential payload has unexpected fields")
        if any(item is not None and not isinstance(item, str) for item in parsed.values()):
            raise ValueError("credential payload has invalid values")
        return cls(**parsed)


@dataclass(frozen=True)
class HostCreate:
    name: str
    address: str
    ssh_port: int
    ssh_username: str
    authentication_method: AuthenticationMethod
    credential: CredentialPayload
    sudo_mode: SudoMode = SudoMode.PASSWORDLESS
    libvirt_uri: str = "qemu:///system"
    labels: tuple[str, ...] = ()
    notes: str | None = None

    def validate(self) -> None:
        if not 1 <= len(self.name.strip()) <= 128 or any(ord(char) < 32 for char in self.name):
            raise ValueError("invalid host name")
        validate_host(self.address)
        validate_port(self.ssh_port)
        if not USERNAME_PATTERN.fullmatch(self.ssh_username):
            raise ValueError("invalid SSH username")
        if self.libvirt_uri != "qemu:///system":
            raise ValueError("unsupported libvirt URI")
        if len(self.labels) > 32 or any(
            not LABEL_PATTERN.fullmatch(label) for label in self.labels
        ):
            raise ValueError("invalid host labels")
        if self.notes is not None and len(self.notes) > 4_000:
            raise ValueError("host notes exceed size limit")
        self.credential.validate(self.authentication_method)
