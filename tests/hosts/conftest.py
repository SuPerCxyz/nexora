from base64 import b64encode
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.credentials import HostCredentialService
from nexora.hosts.onboarding import HostOnboardingService
from nexora.remote.host_key_store import HostKeyStore
from nexora.remote.host_keys import HostKeyCandidate
from nexora.security import CredentialCipher
from nexora.security.keyring import CredentialKeyring


def host_key(value: bytes = b"host-key-one") -> HostKeyCandidate:
    return HostKeyCandidate(
        "kvm.example.test",
        22,
        "ssh-ed25519",
        b64encode(value).decode(),
    )


@dataclass
class HostRuntime:
    database: Database
    onboarding: HostOnboardingService
    credentials: HostCredentialService
    scanner_values: list[HostKeyCandidate]
    store: HostKeyStore


@pytest.fixture
def host_runtime(settings: Settings) -> Iterator[HostRuntime]:
    database = Database(settings)
    upgrade_database(database)
    cipher = CredentialCipher(CredentialKeyring.from_settings(settings))
    scanner_values = [host_key()]

    def scanner(_host: str, _port: int) -> list[HostKeyCandidate]:
        return list(scanner_values)

    store = HostKeyStore(settings.data_dir / "hostkeys")
    runtime = HostRuntime(
        database,
        HostOnboardingService(database, cipher, store, scanner=scanner),
        HostCredentialService(database, cipher),
        scanner_values,
        store,
    )
    try:
        yield runtime
    finally:
        database.dispose()
