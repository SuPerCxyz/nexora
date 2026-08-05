"""Issue, authenticate, expire, and revoke scoped media credentials."""

import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from ipaddress import ip_address
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from nexora.db import Database
from nexora.hosts.models import Host
from nexora.media.models import (
    MediaCredential,
    MediaCredentialStatus,
    MediaItem,
    MediaKind,
    MediaStatus,
)

DEFAULT_TTL = timedelta(days=7)
MAX_TTL = timedelta(days=30)


class MediaCredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class IssuedMediaCredential:
    credential: MediaCredential
    token: str


class MediaCredentialService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def issue(
        self,
        media_item_id: str,
        *,
        host_id: str | None = None,
        vm_uuid: str | None = None,
        ttl: timedelta = DEFAULT_TTL,
    ) -> IssuedMediaCredential:
        if ttl <= timedelta() or ttl > MAX_TTL:
            raise ValueError("media credential TTL is invalid")
        if vm_uuid is not None:
            vm_uuid = str(UUID(vm_uuid))
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        with self.database.session() as session:
            item = session.get(MediaItem, media_item_id)
            if item is None or item.kind != MediaKind.ISO or item.status != MediaStatus.AVAILABLE:
                raise MediaCredentialError("ISO media is unavailable")
            credential = MediaCredential(
                id=str(uuid4()),
                media_item_id=item.id,
                media_sha256=item.sha256,
                host_id=host_id,
                vm_uuid=vm_uuid,
                token_digest=_digest(token),
                status=MediaCredentialStatus.ACTIVE,
                created_at=now,
                expires_at=now + ttl,
            )
            session.add(credential)
            session.flush()
            return IssuedMediaCredential(credential, token)

    def authenticate(self, credential_id: str, token: str) -> MediaItem:
        if not 32 <= len(token) <= 256:
            raise MediaCredentialError("media credential is invalid")
        try:
            credential_id = str(UUID(credential_id))
        except ValueError as exc:
            raise MediaCredentialError("media credential is invalid") from exc
        now = datetime.now(UTC)
        with self.database.session() as session:
            credential = session.get(MediaCredential, credential_id)
            item = self._active_item(session, credential, now)
            assert credential is not None
            if not hmac.compare_digest(_digest(token), credential.token_digest):
                raise MediaCredentialError("media credential is invalid")
            if credential.last_accessed_at is None:
                credential.last_accessed_at = now
            return item

    def issue_for_node(
        self,
        media_item_id: str,
        *,
        host_id: str,
        vm_uuid: str,
        ttl: timedelta = DEFAULT_TTL,
    ) -> MediaCredential:
        """Issue a source-IP-bound credential without exposing its bearer token."""

        return self.issue(
            media_item_id,
            host_id=host_id,
            vm_uuid=vm_uuid,
            ttl=ttl,
        ).credential

    def authenticate_node(self, credential_id: str, client_ip: str) -> MediaItem:
        try:
            credential_id = str(UUID(credential_id))
            source = ip_address(client_ip)
        except ValueError as exc:
            raise MediaCredentialError("media credential is invalid") from exc
        now = datetime.now(UTC)
        with self.database.session() as session:
            credential = session.get(MediaCredential, credential_id)
            item = self._active_item(session, credential, now)
            assert credential is not None
            if credential.host_id is None or credential.vm_uuid is None:
                raise MediaCredentialError("media credential is invalid")
            host = session.get(Host, credential.host_id)
            try:
                expected = ip_address(host.address) if host is not None else None
            except ValueError as exc:
                raise MediaCredentialError("media credential is invalid") from exc
            if expected != source:
                raise MediaCredentialError("media credential is invalid")
            if credential.last_accessed_at is None:
                credential.last_accessed_at = now
            return item

    def revoke(self, credential_id: str) -> bool:
        with self.database.session() as session:
            credential = session.get(MediaCredential, credential_id)
            if credential is None:
                return False
            if credential.status == MediaCredentialStatus.ACTIVE:
                credential.status = MediaCredentialStatus.REVOKED
                credential.revoked_at = datetime.now(UTC)
            return True

    def _active_item(
        self,
        session: Session,
        credential: MediaCredential | None,
        now: datetime,
    ) -> MediaItem:
        if credential is None or credential.status != MediaCredentialStatus.ACTIVE:
            raise MediaCredentialError("media credential is invalid")
        expires_at = credential.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            credential.status = MediaCredentialStatus.EXPIRED
            raise MediaCredentialError("media credential is invalid")
        item = session.get(MediaItem, credential.media_item_id)
        if (
            item is None
            or item.kind != MediaKind.ISO
            or item.status != MediaStatus.AVAILABLE
            or item.sha256 != credential.media_sha256
        ):
            raise MediaCredentialError("media credential is invalid")
        return item


def _digest(token: str) -> str:
    return sha256(token.encode()).hexdigest()
