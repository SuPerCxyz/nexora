import pytest
from sqlalchemy import select

from nexora.hosts.contracts import CredentialPayload, HostCreate
from nexora.hosts.models import (
    AuthenticationMethod,
    Host,
    HostCredential,
    HostFingerprint,
    HostStatus,
)
from nexora.hosts.onboarding import (
    HostConfirmationError,
    HostKeyChangedError,
    candidate_digest,
)

from .conftest import HostRuntime, host_key


def _create() -> HostCreate:
    return HostCreate(
        name="node-one",
        address="kvm.example.test",
        ssh_port=22,
        ssh_username="root",
        authentication_method=AuthenticationMethod.PASSWORD,
        credential=CredentialPayload(password="a-secret-password"),
        labels=("lab",),
    )


def test_begin_persists_only_encrypted_credentials_and_pending_keys(
    host_runtime: HostRuntime,
) -> None:
    host = host_runtime.onboarding.begin(_create())

    assert HostStatus.PENDING_HOST_KEY == host.status
    assert candidate_digest(host_runtime.scanner_values) == host.pending_host_key_digest
    assert CredentialPayload(password="a-secret-password") == host_runtime.credentials.load(host.id)
    with host_runtime.database.session() as session:
        credential = session.scalar(select(HostCredential).where(HostCredential.host_id == host.id))
        fingerprints = list(
            session.scalars(select(HostFingerprint).where(HostFingerprint.host_id == host.id))
        )
        assert credential is not None
        assert "a-secret-password" not in credential.ciphertext
        assert ["pending"] == [item.trust_state for item in fingerprints]


def test_confirm_rescans_then_writes_strict_known_hosts(
    host_runtime: HostRuntime,
) -> None:
    pending = host_runtime.onboarding.begin(_create())

    confirmed = host_runtime.onboarding.confirm(
        pending.id,
        candidate_digest(host_runtime.scanner_values),
    )

    assert HostStatus.READY == confirmed.status
    known_hosts = host_runtime.store.path_for(pending.id)
    assert known_hosts.is_file()
    assert 0o600 == known_hosts.stat().st_mode & 0o777
    assert "ssh-ed25519" in known_hosts.read_text()
    with host_runtime.database.session() as session:
        fingerprints = list(
            session.scalars(select(HostFingerprint).where(HostFingerprint.host_id == pending.id))
        )
        assert ["trusted"] == [item.trust_state for item in fingerprints]


def test_stale_confirmation_digest_is_rejected(host_runtime: HostRuntime) -> None:
    pending = host_runtime.onboarding.begin(_create())

    with pytest.raises(HostConfirmationError, match="stale"):
        host_runtime.onboarding.confirm(pending.id, "0" * 64)

    assert host_runtime.store.path_for(pending.id).exists() is False


def test_host_key_change_between_scan_and_confirm_is_blocked(
    host_runtime: HostRuntime,
) -> None:
    pending = host_runtime.onboarding.begin(_create())
    original_digest = candidate_digest(host_runtime.scanner_values)
    host_runtime.scanner_values[:] = [host_key(b"host-key-two")]

    with pytest.raises(HostKeyChangedError) as captured:
        host_runtime.onboarding.confirm(pending.id, original_digest)

    assert captured.value.previous[0].fingerprint != captured.value.current[0].fingerprint
    assert host_runtime.store.path_for(pending.id).exists() is False
    with host_runtime.database.session() as session:
        stored = session.get(Host, pending.id)
        assert stored is not None
        assert HostStatus.PENDING_HOST_KEY == stored.status
