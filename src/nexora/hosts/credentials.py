"""Decryption boundary for managed-host credentials."""

from sqlalchemy import select

from nexora.db import Database
from nexora.hosts.contracts import CredentialPayload
from nexora.hosts.models import AuthenticationMethod, HostCredential
from nexora.security.credentials import (
    CredentialCipher,
    CredentialDecryptionError,
    EncryptedCredential,
)


class CredentialAccessError(RuntimeError):
    """Credential is missing or its authenticated payload is invalid."""


class HostCredentialService:
    def __init__(self, database: Database, cipher: CredentialCipher) -> None:
        self.database = database
        self.cipher = cipher

    def load(self, host_id: str) -> CredentialPayload:
        with self.database.session() as session:
            stored = session.scalar(select(HostCredential).where(HostCredential.host_id == host_id))
            if stored is None:
                raise CredentialAccessError("host credential is unavailable")
            envelope = EncryptedCredential(
                key_version=stored.key_version,
                nonce=stored.nonce,
                ciphertext=stored.ciphertext,
            )
            credential_id = stored.id
            schema_version = stored.schema_version
            method_value = stored.authentication_method
        try:
            plaintext = self.cipher.decrypt(
                envelope,
                credential_id=credential_id,
                host_id=host_id,
                schema_version=schema_version,
            )
            payload = CredentialPayload.decode(plaintext)
            payload.validate(AuthenticationMethod(method_value))
            return payload
        except (CredentialDecryptionError, ValueError, TypeError):
            raise CredentialAccessError("host credential is unavailable") from None
