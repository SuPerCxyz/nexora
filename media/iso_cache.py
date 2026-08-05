"""Verified platform ISO transfer into the remote temporary cache."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from nexora.media.copy import _require_transfer
from nexora.media.copy_remote import RemoteImageTarget
from nexora.media.models import MediaItem
from nexora.media.ranges import open_indexed_media
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import RemoteExecutor
from nexora.remote.transfer import RemoteFileTransfer

CacheProgress = Callable[[int, str], None]
CACHE_ROOT = PurePosixPath("/var/tmp")


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
        self.target = RemoteImageTarget(executor)

    def ensure(
        self,
        host_id: str,
        media: MediaItem,
        *,
        task_id: str,
        sudo: bool,
        progress: CacheProgress | None = None,
    ) -> CachedIso:
        final_path = cache_path(media.sha256)
        partial_path = f"{final_path}.nexora-{task_id}.partial"
        opened = open_indexed_media(self.library_dir, media)
        completed = False
        _notify(progress, 1, "Validate remote cache space and collision")
        try:
            exists = self.target.prepare(
                host_id,
                CACHE_ROOT,
                final_path,
                partial_path,
                media,
                sudo,
            )
            if exists:
                completed = True
                return CachedIso(final_path, False)
            _notify(progress, 2, "Stream ISO into task-owned partial file")
            result = self.transfer.upload(
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
            )
            _require_transfer(result, media.size_bytes)
            _notify(progress, 3, "Verify cached ISO size")
            if not self.target.size_matches(host_id, partial_path, media, sudo):
                raise RuntimeError("cached ISO size verification failed")
            _notify(progress, 4, "Verify cached ISO SHA-256")
            if not self.target.sha256_matches(host_id, partial_path, media, sudo):
                raise RuntimeError("cached ISO SHA-256 verification failed")
            _notify(progress, 5, "Publish cached ISO without overwrite")
            self.target.publish(host_id, partial_path, final_path, media, sudo)
            completed = True
            return CachedIso(final_path, True)
        finally:
            opened.close()
            if not completed:
                self.target.cleanup_partial(host_id, partial_path, sudo)

    def remove(self, host_id: str, path: str, *, sudo: bool) -> None:
        if path != cache_path_from_name(path):
            raise ValueError("ISO cache path is outside the managed namespace")
        result = self.executor.run(
            host_id,
            CommandSpec("rm", ("-f", "--", path)),
            sudo=sudo,
            timeout=30,
        )
        if result.exit_code != 0 or result.timed_out or result.cancelled:
            raise RuntimeError("cached ISO cleanup failed")


def cache_path(sha256: str) -> str:
    if len(sha256) != 64 or any(value not in "0123456789abcdef" for value in sha256):
        raise ValueError("media SHA-256 is invalid")
    return str(CACHE_ROOT / f"nexora-media-{sha256}.iso")


def cache_path_from_name(path: str) -> str:
    name = PurePosixPath(path).name
    prefix, suffix = "nexora-media-", ".iso"
    digest = name.removeprefix(prefix).removesuffix(suffix)
    return cache_path(digest)


def _notify(progress: CacheProgress | None, sequence: int, message: str) -> None:
    if progress is not None:
        progress(sequence, message)
