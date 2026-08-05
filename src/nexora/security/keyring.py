"""Credential master-key loading and versioning."""

import base64
import binascii
from dataclasses import dataclass

from nexora.config import Settings


class CredentialKeyError(RuntimeError):
    """Raised when credential keys are missing or malformed."""


@dataclass(frozen=True)
class CredentialKeyring:
    """Versioned AES-256 key material."""

    active_version: int
    keys: dict[int, bytes]

    @classmethod
    def from_settings(cls, settings: Settings) -> "CredentialKeyring":
        encoded_key = (
            settings.credential_key.get_secret_value()
            if settings.credential_key is not None
            else _read_key_file(settings)
        )
        if not encoded_key:
            raise CredentialKeyError("NEXORA_CREDENTIAL_KEY or key file is required")

        keys = {settings.credential_active_key_version: _decode_key(encoded_key)}
        if settings.credential_previous_keys is not None:
            previous = settings.credential_previous_keys.get_secret_value()
            for item in filter(None, (part.strip() for part in previous.split(","))):
                version_text, separator, value = item.partition(":")
                if not separator or not version_text.isdecimal():
                    raise CredentialKeyError("previous credential key format is invalid")
                version = int(version_text)
                if version in keys:
                    raise CredentialKeyError("credential key versions must be unique")
                keys[version] = _decode_key(value)
        return cls(settings.credential_active_key_version, keys)

    @property
    def active_key(self) -> bytes:
        return self.keys[self.active_version]

    def key_for(self, version: int) -> bytes:
        try:
            return self.keys[version]
        except KeyError:
            raise CredentialKeyError("credential key version is unavailable") from None


def _read_key_file(settings: Settings) -> str | None:
    path = settings.credential_key_file
    if path is None:
        return None
    try:
        if path.stat().st_size > 1_024:
            raise CredentialKeyError("credential key file is too large")
        return path.read_text(encoding="ascii").strip()
    except OSError as exc:
        raise CredentialKeyError("credential key file cannot be read") from exc


def _decode_key(encoded: str) -> bytes:
    try:
        key = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise CredentialKeyError("credential key must be valid base64") from None
    if len(key) != 32:
        raise CredentialKeyError("credential key must decode to 32 bytes")
    return key
