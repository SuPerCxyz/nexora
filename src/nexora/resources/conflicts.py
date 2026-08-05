"""Fail-closed resource write guards against stale and out-of-band state."""

from dataclasses import dataclass

from nexora.db import Database
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType

BLOCKING_STATUSES = frozenset(
    {
        ResourceStatus.INACCESSIBLE,
        ResourceStatus.MISSING,
        ResourceStatus.STALE,
        ResourceStatus.CHANGED_OUT_OF_BAND,
        ResourceStatus.CONFLICT,
    }
)


@dataclass(frozen=True)
class ResourceBaseVersion:
    resource_id: str
    host_id: str
    resource_type: ResourceType
    native_id: str
    generation: int
    persistent_hash: str | None
    live_hash: str | None


@dataclass(frozen=True)
class VerifiedResourceVersion:
    resource_id: str
    generation: int
    persistent_hash: str | None
    live_hash: str | None


class ResourceWriteConflict(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        base: ResourceBaseVersion,
        current_generation: int | None,
        current_hash: str | None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.base = base
        self.current_generation = current_generation
        self.current_hash = current_hash


class ResourceWriteGuard:
    """Verify a page base after the caller has refreshed remote state."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def verify(self, base: ResourceBaseVersion) -> VerifiedResourceVersion:
        with self.database.session() as session:
            resource = session.get(ResourceIndex, base.resource_id)
            if resource is None:
                raise ResourceWriteConflict(
                    "resource no longer exists in the local index",
                    base=base,
                    current_generation=None,
                    current_hash=None,
                )
            self._verify_identity(resource, base)
            current_hash = resource.persistent_hash or resource.live_hash
            if resource.status in BLOCKING_STATUSES:
                raise ResourceWriteConflict(
                    f"resource status blocks writes: {resource.status}",
                    base=base,
                    current_generation=resource.observed_generation,
                    current_hash=current_hash,
                )
            if base.generation > resource.observed_generation:
                raise ResourceWriteConflict(
                    "resource base generation is invalid",
                    base=base,
                    current_generation=resource.observed_generation,
                    current_hash=current_hash,
                )
            if not _hash_matches(resource, base):
                raise ResourceWriteConflict(
                    "resource changed after the page was opened",
                    base=base,
                    current_generation=resource.observed_generation,
                    current_hash=current_hash,
                )
            return VerifiedResourceVersion(
                resource.id,
                resource.observed_generation,
                resource.persistent_hash,
                resource.live_hash,
            )

    def _verify_identity(
        self,
        resource: ResourceIndex,
        base: ResourceBaseVersion,
    ) -> None:
        if (
            resource.host_id != base.host_id
            or resource.resource_type != base.resource_type
            or resource.native_id != base.native_id
        ):
            raise ResourceWriteConflict(
                "resource identity does not match the requested scope",
                base=base,
                current_generation=resource.observed_generation,
                current_hash=resource.persistent_hash or resource.live_hash,
            )


def _hash_matches(resource: ResourceIndex, base: ResourceBaseVersion) -> bool:
    if resource.persistent_hash is not None or base.persistent_hash is not None:
        return resource.persistent_hash == base.persistent_hash
    return resource.live_hash == base.live_hash and resource.observed_generation == base.generation
