import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nexora.app import create_app
from nexora.config import Settings
from nexora.security.credentials import CredentialCipher, CredentialDecryptionError
from nexora.security.keyring import CredentialKeyError, CredentialKeyring


def _key(value: bytes) -> str:
    return base64.b64encode(value * 32).decode()


def _cipher(key: str, *, version: int = 1, previous: str | None = None) -> CredentialCipher:
    settings = Settings(
        credential_key=key,
        credential_active_key_version=version,
        credential_previous_keys=previous,
        _env_file=None,
    )
    return CredentialCipher(CredentialKeyring.from_settings(settings))


def test_credential_round_trip_uses_unique_nonces() -> None:
    cipher = _cipher(_key(b"a"))

    first = cipher.encrypt(b"secret", credential_id="cred-1", host_id="host-1")
    second = cipher.encrypt(b"secret", credential_id="cred-1", host_id="host-1")

    assert first.nonce != second.nonce
    assert first.ciphertext != second.ciphertext
    assert b"secret" == cipher.decrypt(first, credential_id="cred-1", host_id="host-1")


def test_credential_is_bound_to_aad_and_detects_tampering() -> None:
    cipher = _cipher(_key(b"a"))
    envelope = cipher.encrypt(b"secret", credential_id="cred-1", host_id="host-1")

    with pytest.raises(CredentialDecryptionError):
        cipher.decrypt(envelope, credential_id="cred-1", host_id="other-host")

    ciphertext = bytearray(base64.b64decode(envelope.ciphertext))
    ciphertext[0] ^= 1
    tampered = envelope.__class__(
        envelope.key_version,
        envelope.nonce,
        base64.b64encode(ciphertext).decode(),
    )
    with pytest.raises(CredentialDecryptionError):
        cipher.decrypt(tampered, credential_id="cred-1", host_id="host-1")

    malformed = envelope.__class__(envelope.key_version, "not-base64", envelope.ciphertext)
    with pytest.raises(CredentialDecryptionError):
        cipher.decrypt(malformed, credential_id="cred-1", host_id="host-1")


def test_previous_key_can_decrypt_during_rotation() -> None:
    old_cipher = _cipher(_key(b"a"), version=1)
    envelope = old_cipher.encrypt(b"secret", credential_id="cred-1", host_id="host-1")
    rotated = _cipher(_key(b"b"), version=2, previous=f"1:{_key(b'a')}")

    assert b"secret" == rotated.decrypt(envelope, credential_id="cred-1", host_id="host-1")
    assert 2 == rotated.encrypt(b"new-secret", credential_id="cred-2", host_id="host-1").key_version


def test_missing_or_invalid_key_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(CredentialKeyError):
        CredentialKeyring.from_settings(Settings(_env_file=None))
    with pytest.raises(CredentialKeyError):
        CredentialKeyring.from_settings(
            Settings(credential_key=base64.b64encode(b"short").decode(), _env_file=None)
        )
    with (
        pytest.raises(CredentialKeyError),
        TestClient(create_app(Settings(data_dir=tmp_path, _env_file=None))),
    ):
        pass


def test_key_can_be_loaded_from_read_only_file(tmp_path: Path) -> None:
    key_file = tmp_path / "credential.key"
    key_file.write_text(_key(b"k"), encoding="ascii")
    key_file.chmod(0o400)

    keyring = CredentialKeyring.from_settings(
        Settings(credential_key_file=key_file, _env_file=None)
    )

    assert 32 == len(keyring.active_key)


def test_settings_repr_does_not_expose_key() -> None:
    encoded = _key(b"s")
    settings = Settings(credential_key=encoded, _env_file=None)

    assert encoded not in repr(settings)
