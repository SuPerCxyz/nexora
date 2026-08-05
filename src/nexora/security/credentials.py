"""Authenticated credential encryption envelopes."""

import base64
import binascii
import json
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from nexora.security.keyring import CredentialKeyring

NONCE_BYTES = 12


class CredentialDecryptionError(RuntimeError):
    """Raised without leaking why authenticated decryption failed."""


@dataclass(frozen=True)
class EncryptedCredential:
    """Serializable encrypted credential fields."""

    key_version: int
    nonce: str
    ciphertext: str


class CredentialCipher:
    """Encrypt credential bytes with resource-bound associated data."""

    def __init__(self, keyring: CredentialKeyring) -> None:
        self.keyring = keyring

    def encrypt(
        self,
        plaintext: bytes,
        *,
        credential_id: str,
        host_id: str,
        schema_version: int = 1,
    ) -> EncryptedCredential:
        version = self.keyring.active_version
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(self.keyring.active_key).encrypt(
            nonce,
            plaintext,
            _aad(credential_id, host_id, schema_version, version),
        )
        return EncryptedCredential(
            key_version=version,
            nonce=base64.b64encode(nonce).decode("ascii"),
            ciphertext=base64.b64encode(ciphertext).decode("ascii"),
        )

    def decrypt(
        self,
        envelope: EncryptedCredential,
        *,
        credential_id: str,
        host_id: str,
        schema_version: int = 1,
    ) -> bytes:
        try:
            key = self.keyring.key_for(envelope.key_version)
            nonce = base64.b64decode(envelope.nonce, validate=True)
            ciphertext = base64.b64decode(envelope.ciphertext, validate=True)
            if len(nonce) != NONCE_BYTES:
                raise ValueError
            return AESGCM(key).decrypt(
                nonce,
                ciphertext,
                _aad(credential_id, host_id, schema_version, envelope.key_version),
            )
        except (binascii.Error, InvalidTag, ValueError):
            raise CredentialDecryptionError("credential cannot be decrypted") from None


def _aad(credential_id: str, host_id: str, schema_version: int, key_version: int) -> bytes:
    payload = ["nexora-credential", credential_id, host_id, schema_version, key_version]
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
