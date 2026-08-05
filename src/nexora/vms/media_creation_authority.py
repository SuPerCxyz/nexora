"""Authoritative guards for platform-image VM creation."""

import json
from dataclasses import dataclass
from pathlib import PurePosixPath

from nexora.media.copy import target_directory
from nexora.media.copy_authority import MediaCopyAuthority
from nexora.media.copy_contracts import MediaCopyInput
from nexora.media.models import MediaItem
from nexora.resources.models import ResourceIndex, ResourceType
from nexora.vms.cloud_init import cloud_init_seed_name
from nexora.vms.creation_authority import VmCreationAuthority
from nexora.vms.creation_iso_authority import verify_creation_iso, verify_driver_iso
from nexora.vms.media_creation_contracts import VmMediaCreateInput


class VmMediaCreationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedMediaCreation:
    media: MediaItem
    pool: ResourceIndex
    disk_path: str
    architecture: str
    iso_path: str | None
    driver_iso_path: str | None
    cloud_init_path: str | None


class VmMediaCreationAuthority:
    def __init__(
        self,
        media: MediaCopyAuthority,
        options: VmCreationAuthority,
    ) -> None:
        self.media = media
        self.options = options

    def verify(
        self,
        create: VmMediaCreateInput,
        *,
        task_id: str,
    ) -> VerifiedMediaCreation:
        create.validate()
        self._refresh_iso(create, create.iso_resource_id)
        self._refresh_iso(create, create.driver_iso_resource_id)
        copy_input = media_copy_input(create)
        try:
            with self.media.verify(copy_input, task_id) as resources:
                self._verify_source(resources.media, create)
                path = str(target_directory(resources.pool) / create.target_file_name)
                if not PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
                    raise VmMediaCreationConflict("target image path is invalid")
                self.options.domains.run(create.host_id)
                self.options.refresh_options(create)
                self.options.verify_domain_identity(create)
                self.options.verify_network(create)
                iso_path = verify_creation_iso(
                    self.options.database,
                    self.options.guard,
                    create,
                )
                driver_iso_path = verify_driver_iso(
                    self.options.database,
                    self.options.guard,
                    create,
                )
                seed_name = cloud_init_seed_name(create)
                seed_path = str(target_directory(resources.pool) / seed_name) if seed_name else None
                return VerifiedMediaCreation(
                    resources.media,
                    resources.pool,
                    path,
                    self.options.architecture(create.host_id),
                    iso_path,
                    driver_iso_path,
                    seed_path,
                )
        except VmMediaCreationConflict:
            raise
        except Exception as exc:
            raise VmMediaCreationConflict(str(exc)) from exc

    def _verify_source(self, media: MediaItem, create: VmMediaCreateInput) -> None:
        try:
            backing_chain = json.loads(media.backing_chain_json)
        except json.JSONDecodeError as exc:
            raise VmMediaCreationConflict("platform image metadata is invalid") from exc
        if (
            media.image_format != create.media_format
            or media.kind != create.media_format
            or backing_chain != []
            or media.virtual_size_bytes != create.source_virtual_size_bytes
        ):
            raise VmMediaCreationConflict(
                "platform image format changed or contains an external backing chain"
            )

    def _refresh_iso(self, create: VmMediaCreateInput, resource_id: str | None) -> None:
        if resource_id is None:
            return
        with self.options.database.session() as session:
            volume = session.get(ResourceIndex, resource_id)
            if volume is None or volume.parent_native_id is None:
                raise VmMediaCreationConflict("installation ISO no longer exists")
            pool_uuid = volume.parent_native_id
            volume_name = volume.display_name
        observation = self.options.storage.read_volume(
            create.host_id,
            pool_uuid,
            volume_name,
        )
        self.options.storage.store.refresh_one(
            create.host_id,
            ResourceType.STORAGE_VOLUME,
            observation,
        )


def media_copy_input(create: VmMediaCreateInput) -> MediaCopyInput:
    return MediaCopyInput(
        media_item_id=create.media_item_id,
        media_sha256=create.media_sha256,
        host_id=create.host_id,
        pool_resource_id=create.pool_resource_id,
        pool_native_id=create.pool_uuid,
        pool_generation=create.pool_generation,
        pool_persistent_hash=create.pool_hash,
        target_file_name=create.target_file_name,
    )
