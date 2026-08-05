"""Validated platform image copy into an indexed remote storage pool."""

import json
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from nexora.hosts.models import SudoMode
from nexora.media.copy_authority import MediaCopyAuthority, MediaCopyAuthorityError
from nexora.media.copy_contracts import MediaCopyInput
from nexora.media.copy_errors import MediaCopyCancelled, MediaCopyError
from nexora.media.copy_remote import RemoteImageTarget
from nexora.media.models import MediaItem
from nexora.media.ranges import open_indexed_media
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import RemoteExecutor
from nexora.remote.transfer import RemoteFileTransfer, TransferResult
from nexora.resources.models import ResourceIndex

CopyProgress = Callable[[int, float, str], None]
CancellationCheck = Callable[[], bool]


class MediaImageCopyService:
    def __init__(
        self,
        library_dir: Path,
        executor: RemoteExecutor,
        transfer: RemoteFileTransfer,
        authority: MediaCopyAuthority,
    ) -> None:
        self.library_dir = library_dir
        self.transfer = transfer
        self.authority = authority
        self.remote_target = RemoteImageTarget(executor)

    def execute(
        self,
        copy_input: MediaCopyInput,
        *,
        task_id: str,
        progress: CopyProgress | None = None,
        cancellation_requested: CancellationCheck | None = None,
    ) -> str:
        copy_input.validate()
        try:
            with self.authority.verify(copy_input, task_id) as resources:
                return self._copy_verified(
                    copy_input,
                    resources.media,
                    resources.pool,
                    resources.host.id,
                    resources.host.ssh_username != "root"
                    and resources.host.sudo_mode == SudoMode.PASSWORDLESS,
                    task_id,
                    progress,
                    cancellation_requested,
                )
        except MediaCopyAuthorityError as exc:
            raise MediaCopyError(str(exc)) from exc

    def _copy_verified(
        self,
        copy_input: MediaCopyInput,
        media: MediaItem,
        pool: ResourceIndex,
        host_id: str,
        sudo: bool,
        task_id: str,
        progress: CopyProgress | None,
        cancellation_requested: CancellationCheck | None,
    ) -> str:
        target_kind = PurePosixPath(copy_input.target_file_name).suffix.removeprefix(".")
        if target_kind != media.kind:
            raise MediaCopyError("target extension must match source image format")
        target_dir = target_directory(pool)
        final_path = str(target_dir / copy_input.target_file_name)
        partial_path = str(target_dir / f".{copy_input.target_file_name}.nexora-{task_id}.partial")
        opened = open_indexed_media(self.library_dir, media)
        _notify(progress, 1, 0, "Validate target directory, space, and file names")
        try:
            already_published = self.remote_target.prepare(
                host_id,
                target_dir,
                final_path,
                partial_path,
                media,
                sudo,
            )
        except Exception:
            opened.close()
            raise
        if already_published:
            opened.close()
            return f"image already published; host={host_id}; path={final_path}"
        partial_owned = True
        try:
            _cancel(cancellation_requested)
            _notify(progress, 2, 5, "Stream image to task-owned partial file")
            transfer = self.transfer.upload(
                host_id,
                opened.descriptor,
                CommandSpec(
                    "dd",
                    (
                        f"of={partial_path}",
                        "bs=1048576",
                        "conv=fsync",
                        "status=none",
                    ),
                ),
                sudo=sudo,
                timeout=86_400,
                progress=lambda sent: _notify(
                    progress,
                    2,
                    5 + sent / max(1, media.size_bytes) * 70,
                    f"Copied {sent} of {media.size_bytes} bytes",
                ),
                cancellation_requested=cancellation_requested,
            )
            _require_transfer(transfer, media.size_bytes)
            _notify(progress, 3, 78, "Verify remote file size")
            if not self.remote_target.size_matches(host_id, partial_path, media, sudo):
                raise MediaCopyError("remote image size verification failed")
            _notify(progress, 4, 84, "Verify remote SHA-256")
            if not self.remote_target.sha256_matches(host_id, partial_path, media, sudo):
                raise MediaCopyError("remote image SHA-256 verification failed")
            _cancel(cancellation_requested)
            _notify(progress, 5, 96, "Publish copied image without overwrite")
            self.remote_target.publish(
                host_id,
                partial_path,
                final_path,
                media,
                sudo,
            )
            partial_owned = False
            return f"image copied; host={host_id}; path={final_path}; sha256={media.sha256}"
        finally:
            opened.close()
            if partial_owned:
                self.remote_target.cleanup_partial(host_id, partial_path, sudo)


def target_directory(pool: ResourceIndex) -> PurePosixPath:
    try:
        details = json.loads(pool.details_json)
        value = details["target_path"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise MediaCopyError("target pool path is unavailable") from exc
    if not isinstance(value, str) or "\0" in value:
        raise MediaCopyError("target pool path is invalid")
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts:
        raise MediaCopyError("target pool path is invalid")
    if details.get("pool_type") not in {"dir", "netfs"} or not details.get("active"):
        raise MediaCopyError("target pool is not active and writable")
    return path


def _require_transfer(result: TransferResult, expected_size: int) -> None:
    if result.cancelled:
        raise MediaCopyCancelled("image copy was cancelled")
    if result.exit_code != 0 or result.timed_out or result.bytes_sent != expected_size:
        raise MediaCopyError("image transfer failed or was interrupted")


def _cancel(check: CancellationCheck | None) -> None:
    if check is not None and check():
        raise MediaCopyCancelled("image copy was cancelled")


def _notify(
    progress: CopyProgress | None,
    sequence: int,
    percentage: float,
    message: str,
) -> None:
    if progress is not None:
        progress(sequence, min(99, percentage), message)
