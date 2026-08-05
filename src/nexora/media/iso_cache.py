"""Verified, task-owned platform ISO cache on a managed host."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from nexora.media.copy_errors import MediaCopyCancelled, MediaCopyError
from nexora.media.copy_remote import RemoteImageTarget
from nexora.media.models import MediaItem
from nexora.media.ranges import open_indexed_media
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import RemoteExecutor
from nexora.remote.transfer import RemoteFileTransfer, TransferResult

CACHE_DIRECTORY = PurePosixPath("/var/tmp")
CACHE_PREFIX = "nexora-media-"
Progress = Callable[[int, str], None]


@dataclass(frozen=True)
class CachedIso:
    path: str
    created: bool


class MediaIsoCache:
    def __init__(
        self,
        library_dir: Path,
        executor: RemoteExecutor,
        transfer: RemoteFileTransfer,
    ) -> None:
        self.library_dir = library_dir
        self.executor = executor
        self.transfer = transfer
        self.remote = RemoteImageTarget(executor)

    def ensure(
        self,
        host_id: str,
        media: MediaItem,
        *,
        task_id: str,
        sudo: bool,
        progress: Progress | None = None,
    ) -> CachedIso:
        final_path = self.path_for(media.sha256)
        partial_path = f"{final_path}.nexora-{task_id}.partial"
        opened = open_indexed_media(self.library_dir, media)
        _notify(progress, 1, "Validate remote ISO cache and free space")
        try:
            published = self.remote.prepare(
                host_id,
                CACHE_DIRECTORY,
                final_path,
                partial_path,
                media,
                sudo,
            )
        except Exception:
            opened.close()
            raise
        if published:
            opened.close()
            _notify(progress, 2, "Reuse existing verified ISO cache")
            _notify(progress, 3, "Cached ISO size already verified")
            _notify(progress, 4, "Cached ISO SHA-256 already verified")
            _notify(progress, 5, "Cached ISO is already published")
            return CachedIso(final_path, False)
        partial_owned = True
        try:
            _notify(progress, 2, "Copy platform ISO to task-owned partial file")
            result = self.transfer.upload(
                host_id,
                opened.descriptor,
                CommandSpec(
                    "dd",
                    (f"of={partial_path}", "bs=1048576", "conv=fsync", "status=none"),
                ),
                sudo=sudo,
                timeout=86_400,
            )
            _require_transfer(result, media.size_bytes)
            _notify(progress, 3, "Verify cached ISO size")
            if not self.remote.size_matches(host_id, partial_path, media, sudo):
                raise MediaCopyError("cached ISO size verification failed")
            _notify(progress, 4, "Verify cached ISO SHA-256")
            if not self.remote.sha256_matches(host_id, partial_path, media, sudo):
                raise MediaCopyError("cached ISO SHA-256 verification failed")
            _notify(progress, 5, "Publish cached ISO without overwrite")
            self.remote.publish(host_id, partial_path, final_path, media, sudo)
            partial_owned = False
            return CachedIso(final_path, True)
        finally:
            opened.close()
            if partial_owned:
                self.remote.cleanup_partial(host_id, partial_path, sudo)

    def remove(self, host_id: str, path: str, *, sudo: bool) -> None:
        self.validate_path(path)
        result = self.executor.run(
            host_id,
            CommandSpec("rm", ("-f", "--", path)),
            sudo=sudo,
            timeout=30,
            env={"LC_ALL": "C"},
        )
        if (
            result.exit_code != 0
            or result.timed_out
            or result.cancelled
            or result.stdout_truncated
            or result.stderr_truncated
        ):
            raise MediaCopyError("cached ISO cleanup failed")

    @staticmethod
    def path_for(digest: str) -> str:
        if len(digest) != 64 or any(value not in "0123456789abcdef" for value in digest):
            raise MediaCopyError("media SHA-256 is invalid")
        return str(CACHE_DIRECTORY / f"{CACHE_PREFIX}{digest}.iso")

    @classmethod
    def validate_path(cls, path: str) -> None:
        candidate = PurePosixPath(path)
        if (
            candidate.parent != CACHE_DIRECTORY
            or candidate.name != f"{CACHE_PREFIX}{candidate.name.removeprefix(CACHE_PREFIX)}"
            or not candidate.name.endswith(".iso")
        ):
            raise MediaCopyError("cached ISO path is outside the managed namespace")
        digest = candidate.name.removeprefix(CACHE_PREFIX).removesuffix(".iso")
        if cls.path_for(digest) != path:
            raise MediaCopyError("cached ISO path is invalid")


def _require_transfer(result: TransferResult, expected_size: int) -> None:
    if result.cancelled:
        raise MediaCopyCancelled("ISO cache copy was cancelled")
    if result.exit_code != 0 or result.timed_out or result.bytes_sent != expected_size:
        raise MediaCopyError("ISO cache transfer failed or was interrupted")


def _notify(progress: Progress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)
