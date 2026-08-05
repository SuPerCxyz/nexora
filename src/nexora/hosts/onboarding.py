"""Two-phase SSH Host Key onboarding with encrypted credentials."""

import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from nexora.db import Database
from nexora.hosts.contracts import HostCreate
from nexora.hosts.models import Host, HostCredential, HostFingerprint, HostStatus
from nexora.remote.host_key_scanner import scan_host_keys
from nexora.remote.host_key_store import HostKeyStore
from nexora.remote.host_keys import HostKeyCandidate
from nexora.remote.validation import validate_host
from nexora.security.credentials import CredentialCipher, EncryptedCredential

HostKeyScanner = Callable[[str, int], list[HostKeyCandidate]]


class DuplicateHostError(ValueError):
    """A display name or management endpoint is already registered."""


class HostConfirmationError(ValueError):
    """The pending Host Key confirmation is stale or invalid."""


class HostKeyChangedError(HostConfirmationError):
    """Host Keys changed between discovery and confirmation."""

    def __init__(
        self,
        previous: list[HostKeyCandidate],
        current: list[HostKeyCandidate],
    ) -> None:
        super().__init__("SSH Host Key changed before confirmation")
        self.previous = previous
        self.current = current


class HostOnboardingService:
    """Persist pending trust, then re-scan before making a host usable."""

    def __init__(
        self,
        database: Database,
        cipher: CredentialCipher,
        host_key_store: HostKeyStore,
        *,
        scanner: HostKeyScanner = scan_host_keys,
    ) -> None:
        self.database = database
        self.cipher = cipher
        self.host_key_store = host_key_store
        self.scanner = scanner

    def begin(self, create: HostCreate) -> Host:
        create.validate()
        address = validate_host(create.address)
        candidates = self.scanner(address, create.ssh_port)
        _validate_candidate_target(candidates, address, create.ssh_port)
        host_id = str(uuid4())
        credential_id = str(uuid4())
        now = datetime.now(UTC)
        digest = candidate_digest(candidates)
        envelope = self.cipher.encrypt(
            create.credential.encode(),
            credential_id=credential_id,
            host_id=host_id,
        )
        host = Host(
            id=host_id,
            name=create.name.strip(),
            address=address,
            ssh_port=create.ssh_port,
            ssh_username=create.ssh_username,
            authentication_method=create.authentication_method,
            sudo_mode=create.sudo_mode,
            libvirt_uri=create.libvirt_uri,
            status=HostStatus.PENDING_HOST_KEY,
            pending_host_key_digest=digest,
            labels_json=json.dumps(create.labels, separators=(",", ":")),
            notes=create.notes,
            created_at=now,
            updated_at=now,
        )
        try:
            with self.database.session() as session:
                session.add(host)
                session.add(_credential(credential_id, host_id, create, envelope, now))
                session.add_all(_fingerprints(host_id, candidates, now))
        except IntegrityError:
            raise DuplicateHostError("host name or endpoint already exists") from None
        return host

    def confirm(self, host_id: str, submitted_digest: str) -> Host:
        host, previous = self._pending_host(host_id)
        if not submitted_digest or not _constant_match(
            submitted_digest,
            host.pending_host_key_digest,
        ):
            raise HostConfirmationError("Host Key confirmation is stale")
        current = self.scanner(host.address, host.ssh_port)
        _validate_candidate_target(current, host.address, host.ssh_port)
        if not _constant_match(candidate_digest(current), host.pending_host_key_digest):
            raise HostKeyChangedError(previous, current)
        self.host_key_store.save(host.id, current)
        try:
            return self._mark_trusted(host.id, current)
        except Exception:
            self.host_key_store.delete(host.id)
            raise

    def _pending_host(self, host_id: str) -> tuple[Host, list[HostKeyCandidate]]:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None or host.status != HostStatus.PENDING_HOST_KEY:
                raise HostConfirmationError("host is not awaiting confirmation")
            stored = list(
                session.scalars(
                    select(HostFingerprint)
                    .where(
                        HostFingerprint.host_id == host_id,
                        HostFingerprint.trust_state == "pending",
                    )
                    .order_by(HostFingerprint.key_type)
                )
            )
            candidates = [
                HostKeyCandidate(host.address, host.ssh_port, item.key_type, item.key_data)
                for item in stored
            ]
            return host, candidates

    def _mark_trusted(
        self,
        host_id: str,
        candidates: list[HostKeyCandidate],
    ) -> Host:
        now = datetime.now(UTC)
        current_identities = {candidate.identity for candidate in candidates}
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None or host.status != HostStatus.PENDING_HOST_KEY:
                raise HostConfirmationError("host is not awaiting confirmation")
            fingerprints = list(
                session.scalars(select(HostFingerprint).where(HostFingerprint.host_id == host_id))
            )
            stored_identities = {(item.key_type, item.key_data) for item in fingerprints}
            if stored_identities != current_identities:
                raise HostConfirmationError("stored Host Key set no longer matches")
            for fingerprint in fingerprints:
                fingerprint.trust_state = "trusted"
                fingerprint.trusted_at = now
            host.status = HostStatus.READY
            host.pending_host_key_digest = None
            host.updated_at = now
            host.last_error = None
            return host


def candidate_digest(candidates: list[HostKeyCandidate]) -> str:
    if not candidates:
        raise ValueError("Host Key candidate set is empty")
    identities = sorted((candidate.key_type, candidate.key_data) for candidate in candidates)
    payload = json.dumps(identities, separators=(",", ":")).encode()
    return sha256(payload).hexdigest()


def _validate_candidate_target(
    candidates: list[HostKeyCandidate],
    address: str,
    port: int,
) -> None:
    if not candidates or any(
        candidate.host != address or candidate.port != port for candidate in candidates
    ):
        raise HostConfirmationError("Host Key scanner returned a different endpoint")


def _constant_match(value: str, expected: str | None) -> bool:
    return expected is not None and hmac.compare_digest(value, expected)


def _credential(
    credential_id: str,
    host_id: str,
    create: HostCreate,
    envelope: EncryptedCredential,
    now: datetime,
) -> HostCredential:
    return HostCredential(
        id=credential_id,
        host_id=host_id,
        authentication_method=create.authentication_method,
        key_version=envelope.key_version,
        nonce=envelope.nonce,
        ciphertext=envelope.ciphertext,
        schema_version=1,
        created_at=now,
        updated_at=now,
    )


def _fingerprints(
    host_id: str,
    candidates: list[HostKeyCandidate],
    now: datetime,
) -> list[HostFingerprint]:
    return [
        HostFingerprint(
            host_id=host_id,
            key_type=candidate.key_type,
            key_data=candidate.key_data,
            fingerprint=candidate.fingerprint,
            trust_state="pending",
            discovered_at=now,
        )
        for candidate in candidates
    ]
