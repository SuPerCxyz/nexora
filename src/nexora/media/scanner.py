"""Read-only, root-confined media library scanner."""

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from nexora.media.inspection import ImageInspector, QemuImageInspector
from nexora.media.models import MediaKind
from nexora.media.store import MediaIndexStore, MediaObservation

MAX_MEDIA_FILES = 10_000
MAX_RELATIVE_DEPTH = 32
HASH_CHUNK_SIZE = 4 * 1024 * 1024
ScanProgress = Callable[[int, float, str], None]
CancellationCheck = Callable[[], bool]


class MediaScanError(RuntimeError):
    pass


class MediaScanCancelled(MediaScanError):
    pass


@dataclass(frozen=True)
class MediaCandidate:
    path: Path
    relative_path: str
    kind: MediaKind
    size_bytes: int
    modified_ns: int
    device: int
    inode: int


class MediaScanner:
    def __init__(
        self,
        library_dir: Path,
        store: MediaIndexStore,
        inspector: ImageInspector | None = None,
    ) -> None:
        self.library_dir = library_dir
        self.store = store
        self.inspector = inspector or QemuImageInspector()

    def scan(
        self,
        *,
        progress: ScanProgress | None = None,
        cancellation_requested: CancellationCheck | None = None,
    ) -> str:
        scan = self.store.begin()
        try:
            _notify(progress, 1, 0, "Enumerate media files")
            candidates = self._enumerate()
            _cancel(cancellation_requested)
            observations: list[MediaObservation] = []
            total = max(1, len(candidates))
            for index, candidate in enumerate(candidates):
                _cancel(cancellation_requested)
                percentage = 10 + index / total * 80
                _notify(
                    progress,
                    2,
                    percentage,
                    f"Hash and inspect {candidate.relative_path}",
                )
                observations.append(self._observe(candidate, cancellation_requested))
            _notify(progress, 3, 95, "Commit authoritative media snapshot")
            count = self.store.complete(scan.id, observations)
            return f"media scan complete; files={count}; generation={scan.generation}"
        except Exception as exc:
            self.store.fail(scan.id, str(exc))
            raise

    def _enumerate(self) -> list[MediaCandidate]:
        try:
            root = self.library_dir.resolve(strict=True)
        except OSError as exc:
            raise MediaScanError("media library directory is unavailable") from exc
        if not root.is_dir():
            raise MediaScanError("media library path is not a directory")
        candidates: list[MediaCandidate] = []
        for directory, names, files in os.walk(root, followlinks=False):
            names[:] = sorted(name for name in names if not (Path(directory) / name).is_symlink())
            for name in sorted(files):
                candidate = self._candidate(root, Path(directory) / name)
                if candidate is not None:
                    candidates.append(candidate)
                    if len(candidates) > MAX_MEDIA_FILES:
                        raise MediaScanError("media file count exceeds safety limit")
        return candidates

    def _candidate(self, root: Path, path: Path) -> MediaCandidate | None:
        kind = _kind(path)
        if kind is None or path.is_symlink():
            return None
        try:
            metadata = path.lstat()
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise MediaScanError("media file changed during enumeration") from exc
        if not stat.S_ISREG(metadata.st_mode) or not resolved.is_relative_to(root):
            return None
        relative = resolved.relative_to(root)
        if len(relative.parts) > MAX_RELATIVE_DEPTH:
            raise MediaScanError("media path depth exceeds safety limit")
        relative_path = relative.as_posix()
        if len(relative_path) > 2_048:
            raise MediaScanError("media relative path exceeds safety limit")
        return MediaCandidate(
            resolved,
            relative_path,
            kind,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_dev,
            metadata.st_ino,
        )

    def _observe(
        self,
        candidate: MediaCandidate,
        cancellation_requested: CancellationCheck | None,
    ) -> MediaObservation:
        digest = _hash_candidate(candidate, cancellation_requested)
        image_format: str | None = "iso" if candidate.kind == MediaKind.ISO else None
        virtual_size: int | None = candidate.size_bytes if candidate.kind == MediaKind.ISO else None
        backing_chain: tuple[str, ...] = ()
        if candidate.kind != MediaKind.ISO:
            info = self.inspector.inspect(candidate.path)
            if info.image_format != candidate.kind.value:
                raise MediaScanError("image format does not match file extension")
            image_format = info.image_format
            virtual_size = info.virtual_size_bytes
            backing_chain = tuple(
                _safe_backing_reference(self.library_dir, candidate.path.parent, value)
                for value in info.backing_files
            )
            _verify_candidate(candidate)
        return MediaObservation(
            relative_path=candidate.relative_path,
            file_name=candidate.path.name,
            kind=candidate.kind,
            size_bytes=candidate.size_bytes,
            modified_ns=candidate.modified_ns,
            file_device=candidate.device,
            file_inode=candidate.inode,
            sha256=digest,
            image_format=image_format,
            virtual_size_bytes=virtual_size,
            backing_chain=backing_chain,
            classification=_classification(candidate.relative_path, candidate.kind),
            architecture=_architecture(candidate.relative_path),
        )


def _kind(path: Path) -> MediaKind | None:
    try:
        return MediaKind(path.suffix.lower().removeprefix("."))
    except ValueError:
        return None


def _hash_candidate(
    candidate: MediaCandidate,
    cancellation_requested: CancellationCheck | None,
) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate.path, flags)
    except OSError as exc:
        raise MediaScanError("media file cannot be opened safely") from exc
    digest = sha256()
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        _match_metadata(candidate, metadata)
        while chunk := stream.read(HASH_CHUNK_SIZE):
            _cancel(cancellation_requested)
            digest.update(chunk)
        _match_metadata(candidate, os.fstat(stream.fileno()))
    _verify_candidate(candidate)
    return digest.hexdigest()


def _verify_candidate(candidate: MediaCandidate) -> None:
    try:
        metadata = candidate.path.lstat()
    except OSError as exc:
        raise MediaScanError("media file disappeared during scan") from exc
    _match_metadata(candidate, metadata)


def _match_metadata(candidate: MediaCandidate, metadata: os.stat_result) -> None:
    actual = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
    expected = (
        candidate.device,
        candidate.inode,
        candidate.size_bytes,
        candidate.modified_ns,
    )
    if actual != expected or not stat.S_ISREG(metadata.st_mode):
        raise MediaScanError("media file changed during scan")


def _safe_backing_reference(root: Path, image_directory: Path, value: str) -> str:
    try:
        backing_path = Path(value)
        resolved = (
            backing_path if backing_path.is_absolute() else image_directory / backing_path
        ).resolve(strict=False)
        library_root = root.resolve(strict=True)
    except OSError:
        return "[external]"
    return (
        resolved.relative_to(library_root).as_posix()
        if resolved.is_relative_to(library_root)
        else "[external]"
    )


def _classification(relative_path: str, kind: MediaKind) -> str:
    lowered = relative_path.lower()
    if kind == MediaKind.ISO and "driver" in lowered:
        return "virtio_driver_iso"
    if kind == MediaKind.ISO and "windows" in lowered:
        return "windows_iso"
    if kind == MediaKind.ISO:
        return "linux_iso"
    if "cloud" in lowered:
        return "cloud_image"
    return "windows_image" if "windows" in lowered else "linux_image"


def _architecture(relative_path: str) -> str | None:
    lowered = relative_path.lower()
    if any(value in lowered for value in ("aarch64", "arm64")):
        return "aarch64"
    if any(value in lowered for value in ("x86_64", "amd64")):
        return "x86_64"
    return None


def _cancel(check: CancellationCheck | None) -> None:
    if check is not None and check():
        raise MediaScanCancelled("media scan was cancelled")


def _notify(
    progress: ScanProgress | None,
    sequence: int,
    percentage: float,
    message: str,
) -> None:
    if progress is not None:
        progress(sequence, percentage, message)
